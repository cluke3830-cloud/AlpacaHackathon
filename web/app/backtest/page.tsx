"use client";
import { useEffect, useMemo, useState } from "react";
import TabNav from "@/components/TabNav";
import Plot from "@/components/Plot";
import { LAYOUT, CONFIG, C } from "@/lib/plotTheme";

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

type Percentile = { metric: string; p5: number; p50: number; p95: number; fmt: string };

type Period = {
  available: boolean;
  reason?: string;
  n_days?: number; start?: string; end?: string;
  historical?: { times: string[]; equity: number[] };
  mc?: { curves: number[][]; median: number[]; returns: number[] };
  percentiles?: Percentile[];
  risk_of_ruin?: { level: number; prob: number }[];
  p_loss?: number;
  stats?: Record<string, number | null>;
};

type BT = {
  meta: {
    strategy: string; instrument: string; instrument_note: string; fill: string;
    leverage: number; full_start: string; full_end: string; full_days: number;
    n_paths: number; horizon: number; block: number; generated: string;
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
    const t: any[] = p.mc.curves.map((c) => ({
      y: c, type: "scattergl", mode: "lines",
      line: { color: "rgba(0,231,253,0.05)", width: 1 },
      showlegend: false, hoverinfo: "skip",
    }));
    t.push({
      y: p.mc.median, type: "scatter", mode: "lines", name: "Median expectancy",
      line: { color: C.magenta, width: 3 },
    });
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
        <span className="text-[10px] uppercase tracking-[0.06em] text-label">Backtest period</span>
        <nav className="flex gap-1">
          {bt.period_order.map((k) => {
            const avail = bt.periods[k]?.available;
            return (
              <button key={k}
                onClick={() => avail && setPeriod(k)}
                disabled={!avail}
                title={avail ? undefined : bt.periods[k]?.reason}
                className={`px-2.5 py-0.5 text-xs border transition-colors ${
                  k === period ? "border-cyan text-cyan"
                  : avail ? "border-grid text-label hover:border-label"
                  : "border-grid/40 text-dim cursor-not-allowed line-through"}`}>
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
                ({bt.meta.n_paths.toLocaleString()} universes · {bt.meta.horizon}d ·
                {" "}block bootstrap, {bt.meta.block}d blocks · drawn from {period} of history)
              </span>
            </div>
            <Plot data={mcTraces}
              layout={{ ...LAYOUT, height: 380,
                yaxis: { ...LAYOUT.yaxis, title: { text: "EQUITY (start=100)", font: { size: 9, color: C.label } } },
                xaxis: { ...LAYOUT.xaxis, title: { text: "TRADING DAYS AHEAD", font: { size: 9, color: C.label } } } }}
              config={CONFIG} style={{ width: "100%" }} />
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
                layout={{ ...LAYOUT, height: 260, showlegend: false }}
                config={CONFIG} style={{ width: "100%" }} />
            </section>

            <section className="border border-grid bg-panel/40 p-2">
              <div className="px-1 pb-1 text-[11px] tracking-[0.14em] text-cyan">
                EXPECTED RETURN DISTRIBUTION
                <span className="ml-2 text-label">· {bt.meta.horizon}d forward</span>
              </div>
              <Plot
                data={[{ x: p.mc!.returns, type: "histogram", nbinsx: 50,
                         marker: { color: "#9a31ad" }, opacity: 0.75, name: "Return %" }]}
                layout={{ ...LAYOUT, height: 260, showlegend: false,
                  xaxis: { ...LAYOUT.xaxis, title: { text: `${bt.meta.horizon}-DAY RETURN %`, font: { size: 9, color: C.label } } } }}
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
                  </tr>
                </thead>
                <tbody>
                  {p.percentiles!.map((q) => (
                    <tr key={q.metric} className="border-t border-grid/50">
                      <td className="py-1 text-label">{q.metric}</td>
                      <td className="py-1 text-right text-neg">{fmtV(q.p5, q.fmt)}</td>
                      <td className="py-1 text-right">{fmtV(q.p50, q.fmt)}</td>
                      <td className="py-1 text-right text-pos">{fmtV(q.p95, q.fmt)}</td>
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
