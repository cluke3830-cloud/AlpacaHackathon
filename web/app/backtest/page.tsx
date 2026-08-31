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
 * All numbers are PRECOMPUTED in Python (scripts/export_backtest_json.py) so
 * this tab shows the same figures that went through the audit stack, rather
 * than a second implementation that could quietly disagree with it.
 */

type BT = {
  meta: { strategy: string; instrument: string; fill: string; leverage: number;
          start: string; end: string; n_paths: number; horizon: number; generated: string };
  historical: { times: string[]; equity: number[] };
  mc: { curves: number[][]; median: number[]; returns: number[] };
  stats: Record<string, number | null>;
  percentiles: { metric: string; p5: number; p50: number; p95: number; fmt: string }[];
  risk_of_ruin: { level: number; prob: number }[];
  audit: { label: string; value: string; pass: boolean | null }[];
};

const fmtV = (v: number, fmt: string) =>
  fmt === "usd" ? `$${v.toLocaleString(undefined, { maximumFractionDigits: 0 })}`
    : fmt === "pct" ? `${v.toFixed(2)}%` : v.toFixed(2);

export default function BacktestPage() {
  const [bt, setBt] = useState<BT | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    fetch("/api/backtest")
      .then((r) => r.json())
      .then((d) => (d.error ? setErr(d.error) : setBt(d)))
      .catch((e) => setErr(String(e)));
  }, []);

  const mcTraces = useMemo(() => {
    if (!bt) return [];
    const t: any[] = bt.mc.curves.map((c) => ({
      y: c, type: "scattergl", mode: "lines",
      line: { color: "rgba(0,231,253,0.05)", width: 1 },
      showlegend: false, hoverinfo: "skip",
    }));
    t.push({
      y: bt.mc.median, type: "scatter", mode: "lines", name: "Median expectancy",
      line: { color: C.magenta, width: 3 },
    });
    return t;
  }, [bt]);

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
        <span>· {bt.meta.start} → {bt.meta.end}</span>
        <span className="ml-auto">generated {bt.meta.generated}</span>
      </div>

      <section className="mx-4 border border-grid bg-panel/40 p-2">
        <div className="px-1 pb-1 text-[11px] tracking-[0.14em] text-cyan">
          MONTE CARLO SIMULATIONS
          <span className="ml-2 text-label">
            ({bt.meta.n_paths.toLocaleString()} universes · {bt.meta.horizon}d · block bootstrap)
          </span>
        </div>
        <Plot data={mcTraces}
          layout={{ ...LAYOUT, height: 380,
            yaxis: { ...LAYOUT.yaxis, title: { text: "EQUITY", font: { size: 9, color: C.label } } },
            xaxis: { ...LAYOUT.xaxis, title: { text: "TRADING DAYS AHEAD", font: { size: 9, color: C.label } } } }}
          config={CONFIG} style={{ width: "100%" }} />
      </section>

      <div className="mt-3 grid gap-3 px-4 lg:grid-cols-2">
        <section className="border border-grid bg-panel/40 p-2">
          <div className="px-1 pb-1 text-[11px] tracking-[0.14em] text-cyan">HISTORICAL PERFORMANCE</div>
          <Plot
            data={[{ x: bt.historical.times, y: bt.historical.equity, type: "scatter", mode: "lines",
                     name: "Actual history", line: { color: C.gold, width: 2 } }]}
            layout={{ ...LAYOUT, height: 260, showlegend: false }}
            config={CONFIG} style={{ width: "100%" }} />
        </section>

        <section className="border border-grid bg-panel/40 p-2">
          <div className="px-1 pb-1 text-[11px] tracking-[0.14em] text-cyan">EXPECTED RETURN DISTRIBUTION</div>
          <Plot
            data={[{ x: bt.mc.returns, type: "histogram", nbinsx: 50,
                     marker: { color: "#9a31ad" }, opacity: 0.75, name: "Return %" }]}
            layout={{ ...LAYOUT, height: 260, showlegend: false,
              xaxis: { ...LAYOUT.xaxis, title: { text: "1-YEAR RETURN %", font: { size: 9, color: C.label } } } }}
            config={CONFIG} style={{ width: "100%" }} />
        </section>
      </div>

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
              {bt.percentiles.map((p) => (
                <tr key={p.metric} className="border-t border-grid/50">
                  <td className="py-1 text-label">{p.metric}</td>
                  <td className="py-1 text-right text-neg">{fmtV(p.p5, p.fmt)}</td>
                  <td className="py-1 text-right">{fmtV(p.p50, p.fmt)}</td>
                  <td className="py-1 text-right text-pos">{fmtV(p.p95, p.fmt)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>

        <section className="border border-grid bg-panel/40 p-3">
          <div className="pb-2 text-[11px] tracking-[0.14em] text-cyan">RISK OF RUIN</div>
          {bt.risk_of_ruin.map((r) => (
            <div key={r.level} className="flex items-baseline justify-between border-b border-grid/50 py-1">
              <span className="text-[10px] text-label">P( DD &gt; {r.level}% )</span>
              <span className={`text-xs tabular-nums ${r.prob > 10 ? "text-neg" : "text-body"}`}>
                {r.prob.toFixed(1)}%
              </span>
            </div>
          ))}
          <div className="pt-2 text-[9px] leading-snug text-label">
            Block bootstrap (21d blocks) preserves the real autocorrelation and skew;
            a normal-assumption model would misstate this book&apos;s tail.
          </div>
        </section>

        <section className="border border-grid bg-panel/40 p-3">
          <div className="pb-2 text-[11px] tracking-[0.14em] text-cyan">AUDIT</div>
          {bt.audit.map((a) => (
            <div key={a.label} className="flex items-baseline justify-between border-b border-grid/50 py-1">
              <span className="text-[10px] text-label">{a.label}</span>
              <span className={`text-xs tabular-nums ${
                a.pass === true ? "text-pos" : a.pass === false ? "text-gold" : "text-body"}`}>
                {a.value}
              </span>
            </div>
          ))}
        </section>
      </div>
    </main>
  );
}
