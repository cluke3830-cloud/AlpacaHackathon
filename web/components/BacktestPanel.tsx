"use client";
import { Fragment, useMemo } from "react";
import Plot from "./Plot";
import { C, baseLayout } from "@/lib/theme";
import { monthlyTicks } from "@/lib/dateAxis";
import { backtestTiming, backtestBuyHold, type BacktestStats } from "@/lib/backtest";
import type { Bar } from "@/lib/heikinashi";

// Equity-curve + stats comparison for the Market tab's timing signals, over
// whatever lookback window is currently selected. Frictionless (no cost
// model client-side — see backtest.ts) and situational: the research
// backtests (2bps/switch, longer history) are the source of truth for
// deployment decisions; this panel is for visual/at-a-glance comparison.
export default function BacktestPanel({
  bars, smaBuyDays, smaSellDays, msarBuyDays, msarSellDays, loading,
}: {
  bars: Bar[];
  smaBuyDays: string[]; smaSellDays: string[];
  msarBuyDays: string[]; msarSellDays: string[];
  loading?: boolean;
}) {
  const result = useMemo(() => {
    if (bars.length < 2) return null;
    const bh = backtestBuyHold(bars);
    const sma = backtestTiming(bars, smaBuyDays, smaSellDays);
    const msar = backtestTiming(bars, msarBuyDays, msarSellDays);
    return { bh, sma, msar };
  }, [bars, smaBuyDays, smaSellDays, msarBuyDays, msarSellDays]);

  const fig = useMemo(() => {
    if (!result) return null;
    const x = result.bh.curve.map((p) => p.day);
    const mk = (curve: typeof result.bh.curve, name: string, color: string, width: number) => ({
      type: "scatter", mode: "lines", name,
      x: curve.map((p) => p.day), y: curve.map((p) => p.equity),
      line: { color, width },
    });
    const traces = [
      mk(result.bh.curve, "Buy & Hold", C.label, 1.3),
      mk(result.sma.curve, "SMA timed", C.pos, 1.6),
      mk(result.msar.curve, "MSAR timed", C.cyan, 1.6),
    ];
    const ticks = monthlyTicks(bars.map((b) => b.t));
    const layout = baseLayout({
      height: 260,
      uirevision: "backtest-panel",
      xaxis: { type: "category", gridcolor: C.grid, color: C.text,
               tickmode: "array", tickvals: ticks.tickvals, ticktext: ticks.ticktext },
      yaxis: { gridcolor: C.grid, color: C.text, type: "log",
               title: { text: "growth of $1", font: { size: 9 } } },
      showlegend: true,
      legend: { font: { size: 9, color: C.text }, bgcolor: "rgba(5,10,20,0.7)",
                orientation: "h", x: 0, y: 1.18 },
    });
    return { data: traces, layout };
  }, [result, bars]);

  if (bars.length < 2) {
    return (
      <div className="flex h-[260px] items-center justify-center text-xs text-label">
        {loading ? "loading…" : "no data for this window"}
      </div>
    );
  }
  return (
    <div className={loading ? "opacity-40 transition-opacity" : "transition-opacity"}>
      <Plot data={fig!.data as never} layout={fig!.layout as never}
        config={{ displayModeBar: false, doubleClick: "autosize", scrollZoom: false }}
        style={{ width: "100%" }} useResizeHandler />
      <StatsStrip bh={result!.bh.stats} sma={result!.sma.stats} msar={result!.msar.stats} />
    </div>
  );
}

function StatsStrip({ bh, sma, msar }: { bh: BacktestStats; sma: BacktestStats; msar: BacktestStats }) {
  const rows: [string, BacktestStats, string][] = [
    ["Buy & Hold", bh, C.label],
    ["SMA timed", sma, C.pos],
    ["MSAR timed", msar, C.cyan],
  ];
  const pct = (v: number) => `${v >= 0 ? "+" : ""}${(100 * v).toFixed(1)}%`;
  return (
    <div className="grid grid-cols-5 gap-x-3 gap-y-1 px-2 pb-2 pt-2 text-[10px] font-mono">
      <span className="text-dim uppercase tracking-[0.06em]"></span>
      <span className="text-dim uppercase tracking-[0.06em]">CAGR</span>
      <span className="text-dim uppercase tracking-[0.06em]">Sharpe</span>
      <span className="text-dim uppercase tracking-[0.06em]">Max DD</span>
      <span className="text-dim uppercase tracking-[0.06em]">% Long</span>
      {rows.map(([label, s, color]) => (
        <Fragment key={label}>
          <span style={{ color }}>{label}</span>
          <span className="text-body">{pct(s.cagr)}</span>
          <span className="text-body">{s.sharpe.toFixed(2)}</span>
          <span className="text-body">{pct(s.maxDrawdown)}</span>
          <span className="text-body">{(100 * s.pctTimeLong).toFixed(0)}%</span>
        </Fragment>
      ))}
    </div>
  );
}
