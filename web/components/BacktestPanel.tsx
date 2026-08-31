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
export type OptionCurve = {
  times: string[];        // isoDay, ascending
  equity: number[];       // growth of $1 over the FULL history
  in_market: number[];    // 0/1 per day (either sleeve holding)
  coverage_end: string;
};

// Align OUR OPTION BOOK's precomputed curve to the panel's visible window and
// REBASE it to $1 at the first shared day, so all four lines start together
// regardless of lookback. Stats are recomputed over the aligned slice (same
// math as runBacktest) so every row on the strip describes the SAME window --
// full-history stats next to windowed ones would be a quiet apples-to-oranges.
function alignOptionCurve(bars: Bar[], oc: OptionCurve) {
  const eqByDay = new Map(oc.times.map((d, i) => [d, i]));
  const days: string[] = []; const eq: number[] = []; let longDays = 0;
  for (const b of bars) {
    const d = isoDayLocal(b.t);
    const i = eqByDay.get(d);
    if (i == null) continue;               // outside our chain coverage
    days.push(d); eq.push(oc.equity[i]);
    if (oc.in_market[i]) longDays++;
  }
  if (eq.length < 2) return null;
  const base = eq[0];
  const curve = days.map((day, i) => ({ day, equity: eq[i] / base }));
  const rets: number[] = [];
  for (let i = 1; i < eq.length; i++) rets.push(Math.log(eq[i] / eq[i - 1]));
  const mean = rets.reduce((a, b) => a + b, 0) / rets.length;
  const sd = Math.sqrt(rets.reduce((a, b) => a + (b - mean) ** 2, 0) / (rets.length - 1));
  let peak = -Infinity, maxDD = 0;
  for (const p of curve) { peak = Math.max(peak, p.equity); maxDD = Math.min(maxDD, p.equity / peak - 1); }
  const years = rets.length / 252;
  const stats: BacktestStats = {
    cagr: years > 0 ? Math.pow(curve[curve.length - 1].equity, 1 / years) - 1 : 0,
    sharpe: sd > 0 ? (mean / sd) * Math.sqrt(252) : 0,
    maxDrawdown: maxDD,
    pctTimeLong: days.length ? longDays / days.length : 0,
    nDays: days.length,
  };
  return { curve, stats };
}

function isoDayLocal(tSec: number): string {
  return new Date(tSec * 1000).toISOString().slice(0, 10);
}

export default function BacktestPanel({
  bars, smaBuyDays, smaSellDays, msarBuyDays, msarSellDays, optionCurve, loading,
}: {
  bars: Bar[];
  smaBuyDays: string[]; smaSellDays: string[];
  msarBuyDays: string[]; msarSellDays: string[];
  optionCurve?: OptionCurve | null;   // OUR AGENT's real cost-charged book, 1.0x
  loading?: boolean;
}) {
  const result = useMemo(() => {
    if (bars.length < 2) return null;
    const bh = backtestBuyHold(bars);
    const sma = backtestTiming(bars, smaBuyDays, smaSellDays);
    const msar = backtestTiming(bars, msarBuyDays, msarSellDays);
    const opt = optionCurve ? alignOptionCurve(bars, optionCurve) : null;
    return { bh, sma, msar, opt };
  }, [bars, smaBuyDays, smaSellDays, msarBuyDays, msarSellDays, optionCurve]);

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
    if (result.opt) {
      traces.push(mk(result.opt.curve, "Option book (ours)", C.gold, 2.0));
    }
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
      <StatsStrip bh={result!.bh.stats} sma={result!.sma.stats} msar={result!.msar.stats}
        opt={result!.opt?.stats ?? null} />
    </div>
  );
}

function StatsStrip({ bh, sma, msar, opt }: {
  bh: BacktestStats; sma: BacktestStats; msar: BacktestStats; opt: BacktestStats | null;
}) {
  const rows: [string, BacktestStats, string][] = [
    ["Buy & Hold", bh, C.label],
    ["SMA timed", sma, C.pos],
    ["MSAR timed", msar, C.cyan],
  ];
  // Ours goes last and is the only COST-CHARGED row on the strip -- the three
  // above are frictionless overlays (see backtest.ts header). %Long for ours
  // means "either sleeve holding", not literally long.
  if (opt) rows.push(["Option book (ours)", opt, C.gold]);
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
