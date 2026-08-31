"use client";
import { useEffect, useMemo, useState } from "react";
import TabNav from "@/components/TabNav";
import Plot from "@/components/Plot";
import { layout, axisTitle, CONFIG, C } from "@/lib/plotTheme";

/**
 * BACKTESTED tab — same three-row format as Partner_Strategy_2_Backtesting.py:
 *   row 1  Monte Carlo spaghetti (faint cyan) + median (magenta)
 *   row 2  Historical performance (yellow)
 *   row 3  Expected return distribution (purple histogram)
 * plus that script's percentile table (P5 / P50 / P95) and Risk-of-Ruin lines.
 *
 * The LOOKBACK selector changes how much history the bootstrap may draw from --
 * 1Y by default. It is a real re-run per period (each has its own MC, its own
 * percentiles and its own historical slice), not one dataset re-cropped.
 *
 * All numbers are PRECOMPUTED in Python (scripts/export_backtest_json.py) so
 * this tab shows the same figures that went through the audit stack, rather
 * than a second implementation that could quietly disagree with it.
 */

type Percentile = { metric: string; p5: number; p50: number; p95: number;
                    actual: number; fmt: string };

type Period = {
  available: boolean;
  reason?: string;
  n_days?: number; start?: string; end?: string;
  historical?: { times: string[]; equity: number[] };
  mc?: {
    curves: number[][];
    bands: { p5: number[]; p25: number[]; p50: number[]; p75: number[]; p95: number[] };
    actual: number[];
    returns: number[];
    horizon: number; step: number;
    actual_terminal: number; actual_maxdd: number;
    rank_return: number; rank_maxdd: number;
  };
  percentiles?: Percentile[];
  risk_of_ruin?: { level: number; prob: number }[];
  p_loss?: number;
  stats?: Record<string, number | null>;
};

type BT = {
  meta: {
    strategy: string; instrument: string; instrument_note: string; fill: string;
    leverage: number; full_start: string; full_end: string; full_days: number;
    n_paths: number; block: number; generated: string;
  };
  default_period: string;
  period_order: string[];
  periods: Record<string, Period>;
  audit: { label: string; value: string; ok: boolean | null }[];
};

const fmtV = (v: number, fmt: string) =>
  fmt === "usd" ? `$${v.toLocaleString(undefined, { maximumFractionDigits: 0 })}`
    : fmt === "pct" ? `${v.toFixed(2)}%` : v.toFixed(2);

const fmtStat = (v: number | null | undefined, pct = false) =>
  v == null || !isFinite(v) ? "—" : pct ? `${(100 * v).toFixed(1)}%` : v.toFixed(2);

export default function BacktestPage() {
  const [bt, setBt] = useState<BT | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [period, setPeriod] = useState<string>("1Y");

  useEffect(() => {
    fetch("/api/backtest")
      .then((r) => r.json())
      .then((d) => {
        if (d.error) { setErr(d.error); return; }
        setBt(d);
        setPeriod(d.default_period ?? "1Y");
      })
      .catch((e) => setErr(String(e)));
  }, []);

  const p: Period | null = bt ? bt.periods[period] ?? null : null;

  const mcTraces = useMemo(() => {
    if (!p?.available || !p.mc) return [];
    const m = p.mc;
    const x = m.actual.map((_, i) => i * m.step);
    const t: any[] = [];

    // Percentile envelope first (drawn underneath everything else). Computed
    // over ALL 10,000 paths, unlike the spaghetti which is a 200-path sample.
    const band = (hi: number[], lo: number[], color: string, name: string) => {
      t.push({ x, y: hi, type: "scatter", mode: "lines", line: { width: 0 },
               showlegend: false, hoverinfo: "skip" });
      t.push({ x, y: lo, type: "scatter", mode: "lines", line: { width: 0 },
               fill: "tonexty", fillcolor: color, name, hoverinfo: "skip" });
    };
    band(m.bands.p95, m.bands.p5, "rgba(0,231,253,0.07)", "5–95%");
    band(m.bands.p75, m.bands.p25, "rgba(0,231,253,0.14)", "25–75%");

    // A thin sample of individual alternative histories, for texture.
    for (const c of m.curves) {
      t.push({ x, y: c, type: "scattergl", mode: "lines",
               line: { color: "rgba(0,231,253,0.05)", width: 1 },
               showlegend: false, hoverinfo: "skip" });
    }

    t.push({ x, y: m.bands.p50, type: "scatter", mode: "lines",
             name: "Median counterfactual", line: { color: C.magenta, width: 2.5 } });

    // WHAT ACTUALLY HAPPENED — the point of the whole panel.
    t.push({ x, y: m.actual, type: "scatter", mode: "lines",
             name: `ACTUAL (${m.rank_return.toFixed(0)}th pct)`,
             line: { color: C.gold, width: 3 },
             hovertemplate: "day %{x}<br>%{y:.1f}<extra>ACTUAL</extra>" });
    return t;
  }, [p]);

  if (err) {
    return (
      <main className="min-h-screen">
        <TabNav active="/backtest" />
        <div className="mx-4 mt-4 border border-gold/50 bg-gold/5 px-4 py-3 text-xs text-gold">
          {err}
          <div className="mt-2 text-label">
            Generate it with:{" "}
            <code className="text-body">python3 AlpacaHackathon/scripts/export_backtest_json.py</code>
          </div>
        </div>
      </main>
    );
  }
  if (!bt) {
    return (
      <main className="min-h-screen">
        <TabNav active="/backtest" />
        <div className="px-4 py-6 text-xs text-label">loading backtest…</div>
      </main>
    );
  }

  return (
    <main className="min-h-screen">
      <TabNav active="/backtest" />

      <div className="flex flex-wrap items-baseline gap-3 px-4 py-2 text-[10px] text-label">
        <span className="text-[11px] tracking-[0.14em] text-cyan">{bt.meta.strategy}</span>
        <span>{bt.meta.instrument}</span>
        <span>· {bt.meta.fill}</span>
        <span>· {bt.meta.leverage.toFixed(2)}x</span>
        <span className="ml-auto">generated {bt.meta.generated}</span>
      </div>

      {/* ---- lookback selector ---- */}
      <div className="flex flex-wrap items-center gap-3 border-b border-headerline
        bg-gradient-to-r from-[#0A1628] to-[#051020] px-4 py-2">
        <span className="text-[10px] uppercase tracking-[0.06em] text-label">
          Backtest period <span className="text-dim">— click to switch</span>
        </span>
        <nav className="flex gap-1">
          {bt.period_order.map((k) => {
            const avail = bt.periods[k]?.available;
            return (
              <button key={k}
                onClick={() => avail && setPeriod(k)}
                disabled={!avail}
                title={avail ? undefined : bt.periods[k]?.reason}
                className={`px-3 py-1 text-xs border transition-colors ${
                  k === period
                    ? "border-cyan bg-cyan/10 text-cyan font-bold"
                    : avail
                      // Selectable periods read as BRIGHT and clickable. They were
                      // previously dim grey next to the active cyan, which — with a
                      // struck-through 10Y sitting beside them — made the whole row
                      // look locked rather than like a live selector.
                      ? "border-label/70 text-body cursor-pointer hover:border-cyan hover:text-cyan hover:bg-cyan/5"
                      : "border-grid/40 text-dim cursor-not-allowed line-through opacity-50"}`}>
                {k}
              </button>
            );
          })}
        </nav>
        {p?.available && (
          <span className="text-[10px] text-label">
            {p.n_days} sessions · {p.start} → {p.end}
          </span>
        )}
        <span className="ml-auto text-[9px] text-dim">
          full history {bt.meta.full_days}d ({(bt.meta.full_days / 252).toFixed(1)}y):{" "}
          {bt.meta.full_start} → {bt.meta.full_end}
        </span>
      </div>

      {!p?.available ? (
        <div className="mx-4 mt-4 border border-gold/50 bg-gold/5 px-4 py-3 text-xs text-gold">
          <span className="font-bold">{period} unavailable.</span>{" "}
          {p?.reason ?? "no data for this period"}
          <div className="mt-2 text-label">
            Shown as unavailable rather than silently truncated — a {period} label over a
            shorter sample would misstate what the numbers are based on.
          </div>
        </div>
      ) : (
        <>
          {/* ---- row 1: Monte Carlo ---- */}
          <section className="mx-4 mt-3 border border-grid bg-panel/40 p-2">
            <div className="px-1 pb-1 text-[11px] tracking-[0.14em] text-cyan">
              MONTE CARLO SIMULATIONS
              <span className="ml-2 text-label">
                ({bt.meta.n_paths.toLocaleString()} paths · {p.mc!.horizon}d ·
                {" "}block bootstrap, {bt.meta.block}d blocks)
              </span>
            </div>
            <div className="px-1 pb-2 text-[10px] leading-snug text-label">
              What <span className="text-body">could have</span> happened over this same {period}:
              every path is an alternative history of identical length, block-resampled from the
              period&apos;s own returns.{" "}
              <span className="text-gold">Gold = what actually happened.</span>{" "}
              <span className="text-dim">
                Not a forward forecast — the question is whether the backtest was a typical
                outcome of this process or a lucky draw.
              </span>
            </div>
            <Plot data={mcTraces}
              layout={layout({ height: 400,
                // type is EXPLICIT: these are day counts, and Plotly's
                // autotyping once rendered them as epoch dates ("Jan 1256")
                // after a shared axis object leaked from the date chart below.
                xaxis: { type: "linear", title: axisTitle("TRADING DAY OF PERIOD") },
                yaxis: { type: "linear", title: axisTitle("EQUITY (start=100)") } })}
              config={CONFIG} style={{ width: "100%" }} />

            <div className="mt-1 grid grid-cols-2 gap-px bg-grid p-px md:grid-cols-4">
              {[
                ["ACTUAL RETURN", `${p.mc!.actual_terminal >= 0 ? "+" : ""}${p.mc!.actual_terminal.toFixed(1)}%`, C.gold],
                ["MEDIAN COUNTERFACTUAL", `${p.percentiles![1].p50 >= 0 ? "+" : ""}${p.percentiles![1].p50.toFixed(1)}%`, C.magenta],
                ["ACTUAL RANK — RETURN", `${p.mc!.rank_return.toFixed(0)}th pct`,
                  p.mc!.rank_return > 80 ? C.neg : p.mc!.rank_return < 20 ? C.pos : undefined],
                ["ACTUAL RANK — MAX DD", `${p.mc!.rank_maxdd.toFixed(0)}th pct`,
                  p.mc!.rank_maxdd > 80 ? C.neg : undefined],
              ].map(([label, value, tone]) => (
                <div key={label as string} className="bg-bg px-3 py-2">
                  <div className="text-[9px] tracking-[0.08em] text-label">{label}</div>
                  <div className="text-sm tabular-nums"
                       style={tone ? { color: tone as string } : undefined}>{value}</div>
                </div>
              ))}
            </div>
            <div className="px-1 pt-1.5 text-[9px] leading-snug text-dim">
              {p.mc!.rank_return >= 35 && p.mc!.rank_return <= 65
                ? `Reality landed near the middle of its own distribution (${p.mc!.rank_return.toFixed(0)}th percentile) — the backtest looks like a TYPICAL outcome of this process, not an outlier that got lucky.`
                : p.mc!.rank_return > 65
                  ? `Reality landed in the upper ${(100 - p.mc!.rank_return).toFixed(0)}% of its own distribution — the realized backtest was FAVOURABLE relative to what this process typically produces. Size to the median, not to this.`
                  : `Reality landed in the bottom ${p.mc!.rank_return.toFixed(0)}% of its own distribution — the realized backtest UNDERPERFORMED what this process typically produces.`}
            </div>
          </section>

          {/* ---- realized stats for the selected window ---- */}
          <div className="mx-4 mt-3 grid grid-cols-2 gap-px bg-grid p-px md:grid-cols-3 lg:grid-cols-6">
            {[
              ["SHARPE", fmtStat(p.stats?.sharpe)],
              ["CAGR", fmtStat(p.stats?.cagr, true)],
              ["MAX DD", fmtStat(p.stats?.maxdd, true)],
              ["CALMAR", fmtStat(p.stats?.calmar)],
              ["P(LOSING YEAR)", `${(p.p_loss ?? 0).toFixed(1)}%`],
              ["SESSIONS", String(p.n_days ?? 0)],
            ].map(([label, value]) => (
              <div key={label} className="bg-bg px-3 py-2">
                <div className="text-[9px] tracking-[0.08em] text-label">{label}</div>
                <div className="text-sm tabular-nums text-body">{value}</div>
              </div>
            ))}
          </div>

          {/* ---- rows 2 & 3 ---- */}
          <div className="mt-3 grid gap-3 px-4 lg:grid-cols-2">
            <section className="border border-grid bg-panel/40 p-2">
              <div className="px-1 pb-1 text-[11px] tracking-[0.14em] text-cyan">
                HISTORICAL PERFORMANCE
                <span className="ml-2 text-label">· {period} realized, indexed to 100</span>
              </div>
              <Plot
                data={[{ x: p.historical!.times, y: p.historical!.equity,
                         type: "scatter", mode: "lines", name: "Actual history",
                         line: { color: C.gold, width: 2 } }]}
                layout={layout({ height: 260, showlegend: false,
                  xaxis: { type: "date" }, yaxis: { type: "linear" } })}
                config={CONFIG} style={{ width: "100%" }} />
            </section>

            <section className="border border-grid bg-panel/40 p-2">
              <div className="px-1 pb-1 text-[11px] tracking-[0.14em] text-cyan">
                EXPECTED RETURN DISTRIBUTION
                <span className="ml-2 text-label">· {period} counterfactual</span>
              </div>
              <Plot
                data={[{ x: p.mc!.returns, type: "histogram", nbinsx: 50,
                         marker: { color: "#9a31ad" }, opacity: 0.75, name: "Return %" }]}
                layout={layout({ height: 260, showlegend: false,
                  xaxis: { type: "linear", title: axisTitle(`${period} RETURN %`) },
                  yaxis: { type: "linear" },
                  shapes: [{ type: "line", yref: "paper", y0: 0, y1: 1,
                             x0: p.mc!.actual_terminal, x1: p.mc!.actual_terminal,
                             line: { color: C.gold, width: 2 } }],
                  annotations: [{ x: p.mc!.actual_terminal, yref: "paper", y: 1.04,
                                  text: "ACTUAL", showarrow: false,
                                  font: { size: 9, color: C.gold } }] })}
                config={CONFIG} style={{ width: "100%" }} />
            </section>
          </div>

          {/* ---- tables ---- */}
          <div className="mt-3 grid gap-3 px-4 pb-8 lg:grid-cols-3">
            <section className="border border-grid bg-panel/40 p-3">
              <div className="pb-2 text-[11px] tracking-[0.14em] text-cyan">PERCENTILES</div>
              <table className="w-full text-[11px] tabular-nums">
                <thead className="text-[9px] tracking-[0.08em] text-label">
                  <tr>
                    <th className="py-1 text-left font-normal">METRIC</th>
                    <th className="py-1 text-right font-normal">5th</th>
                    <th className="py-1 text-right font-normal">P50</th>
                    <th className="py-1 text-right font-normal">95th</th>
                    <th className="py-1 text-right font-normal text-gold">ACTUAL</th>
                  </tr>
                </thead>
                <tbody>
                  {p.percentiles!.map((q) => (
                    <tr key={q.metric} className="border-t border-grid/50">
                      <td className="py-1 text-label">{q.metric}</td>
                      <td className="py-1 text-right text-neg">{fmtV(q.p5, q.fmt)}</td>
                      <td className="py-1 text-right">{fmtV(q.p50, q.fmt)}</td>
                      <td className="py-1 text-right text-pos">{fmtV(q.p95, q.fmt)}</td>
                      <td className="py-1 text-right text-gold">{fmtV(q.actual, q.fmt)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </section>

            <section className="border border-grid bg-panel/40 p-3">
              <div className="pb-2 text-[11px] tracking-[0.14em] text-cyan">RISK OF RUIN</div>
              {p.risk_of_ruin!.map((r) => (
                <div key={r.level} className="flex items-baseline justify-between border-b border-grid/50 py-1">
                  <span className="text-[10px] text-label">P( DD &gt; {r.level}% )</span>
                  <span className={`text-xs tabular-nums ${r.prob > 10 ? "text-neg" : "text-body"}`}>
                    {r.prob.toFixed(1)}%
                  </span>
                </div>
              ))}
              <div className="pt-2 text-[9px] leading-snug text-label">
                {bt.meta.block}d blocks preserve the real autocorrelation and skew;
                iid draws would manufacture a friendlier distribution than this book has.
              </div>
            </section>

            <section className="border border-grid bg-panel/40 p-3">
              <div className="pb-2 text-[11px] tracking-[0.14em] text-cyan">AUDIT</div>
              {bt.audit.map((a) => (
                <div key={a.label} className="flex items-baseline justify-between border-b border-grid/50 py-1">
                  <span className="text-[10px] text-label">{a.label}</span>
                  <span className={`text-xs tabular-nums ${
                    a.ok === true ? "text-pos" : a.ok === false ? "text-gold" : "text-body"}`}>
                    {a.value}
                  </span>
                </div>
              ))}
              <div className="pt-2 text-[9px] leading-snug text-dim">{bt.meta.instrument_note}</div>
            </section>
          </div>
        </>
      )}
    </main>
  );
}
