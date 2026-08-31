import type { Bar } from "./heikinashi";
import { isoDay } from "./dateAxis";

// Causal backtest utility for the Market tab's timing signals (SMA, MSAR).
// Position at close t earns the t -> t+1 log return (never same-day) — the
// exact convention used throughout research/vix_drawdown/*.py. Frontier
// note: costs are NOT modeled here (client-side, no execution assumptions
// to defend) — the research backtests (2bps/switch) already establish the
// signals survive real friction; this panel is for situational/visual
// comparison against buy-and-hold, not a claim of net-of-cost performance.

export interface BacktestPoint {
  day: string;
  equity: number;   // cumulative growth of $1, starting at the first bar
}

export interface BacktestStats {
  cagr: number;
  sharpe: number;
  maxDrawdown: number;   // negative fraction, e.g. -0.27
  pctTimeLong: number;   // fraction of days in position
  nDays: number;
}

export interface BacktestResult {
  curve: BacktestPoint[];
  stats: BacktestStats;
}

// bars: price bars ascending (e.g. SPY). buyDays/sellDays: isoDay sets from
// a signal's hysteresis output (see vixMeanRev.ts / msarRegime.ts). The
// position starts LONG (matches both signals' own convention) and flips on
// the exact day a buy/sell transition is recorded.
export function backtestTiming(bars: Bar[], buyDays: string[], sellDays: string[]): BacktestResult {
  const buySet = new Set(buyDays);
  const sellSet = new Set(sellDays);
  const positions: number[] = [];
  let isLong = true;
  for (const b of bars) {
    const d = isoDay(b.t);
    if (isLong && sellSet.has(d)) isLong = false;
    else if (!isLong && buySet.has(d)) isLong = true;
    positions.push(isLong ? 1 : 0);
  }
  return runBacktest(bars, positions);
}

// Always-long reference curve (buy & hold), same equity convention.
export function backtestBuyHold(bars: Bar[]): BacktestResult {
  return runBacktest(bars, bars.map(() => 1));
}

function runBacktest(bars: Bar[], positions: number[]): BacktestResult {
  const n = bars.length;
  const curve: BacktestPoint[] = [];
  const dailyReturns: number[] = [];
  let equity = 1;
  let peak = 1;
  let maxDD = 0;
  let longDays = 0;

  if (n > 0) curve.push({ day: isoDay(bars[0].t), equity: 1 });
  for (let i = 0; i < n - 1; i++) {
    const ret = Math.log(bars[i + 1].c / bars[i].c);
    const pos = positions[i];
    if (pos > 0) longDays++;
    const pnl = pos * ret;
    dailyReturns.push(pnl);
    equity *= Math.exp(pnl);
    peak = Math.max(peak, equity);
    maxDD = Math.min(maxDD, equity / peak - 1);
    curve.push({ day: isoDay(bars[i + 1].t), equity });
  }
  // last bar's own position (no next-day return exists yet, but it counts
  // toward %time-long since the signal IS in that state on that day)
  if (n > 0 && positions[n - 1] > 0) longDays++;

  const nRet = dailyReturns.length;
  const mean = nRet > 0 ? dailyReturns.reduce((a, b) => a + b, 0) / nRet : 0;
  const variance = nRet > 1
    ? dailyReturns.reduce((a, b) => a + (b - mean) ** 2, 0) / (nRet - 1)
    : 0;
  const std = Math.sqrt(variance);
  const sharpe = std > 0 ? (mean / std) * Math.sqrt(252) : 0;
  const years = nRet / 252;
  const cagr = years > 0 ? Math.pow(equity, 1 / years) - 1 : 0;

  return {
    curve,
    stats: {
      cagr, sharpe, maxDrawdown: maxDD,
      pctTimeLong: n > 0 ? longDays / n : 0,
      nDays: n,
    },
  };
}
