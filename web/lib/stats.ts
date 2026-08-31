/**
 * Pure performance math for the Stats panel. No I/O, no React -- unit-testable
 * on its own, which matters because these are the numbers the whole terminal
 * is judged on.
 *
 * CONVENTION NOTE, stated because it is the usual source of disagreement
 * between two dashboards: every annualized figure below uses 252 trading days
 * and SIMPLE (not log) returns, matching the Python research side
 * (option_sleeves.stats / option_stats_report.py). If these ever disagree with
 * the backtest numbers, this convention is the first place to look.
 */

export const ANN = 252;

export function toReturns(equity: number[]): number[] {
  const r: number[] = [];
  for (let i = 1; i < equity.length; i++) {
    const prev = equity[i - 1];
    r.push(prev > 0 ? equity[i] / prev - 1 : 0);
  }
  return r;
}

export function mean(x: number[]): number {
  return x.length ? x.reduce((a, b) => a + b, 0) / x.length : 0;
}

export function std(x: number[]): number {
  if (x.length < 2) return 0;
  const m = mean(x);
  return Math.sqrt(x.reduce((a, b) => a + (b - m) ** 2, 0) / (x.length - 1));
}

export function sharpe(returns: number[]): number | null {
  const s = std(returns);
  if (!returns.length || s === 0) return null;
  return (mean(returns) / s) * Math.sqrt(ANN);
}

/** Downside deviation only -- the asymmetry is the point of reporting it. */
export function sortino(returns: number[]): number | null {
  const dn = returns.filter((r) => r < 0);
  if (dn.length < 2) return null;
  const ds = std(dn);
  if (ds === 0) return null;
  return (mean(returns) / ds) * Math.sqrt(ANN);
}

export function maxDrawdown(equity: number[]): number {
  let peak = -Infinity;
  let mdd = 0;
  for (const v of equity) {
    if (v > peak) peak = v;
    if (peak > 0) mdd = Math.min(mdd, v / peak - 1);
  }
  return mdd;
}

/**
 * Historical VaR: the q-quantile of the realized return distribution.
 * Historical rather than parametric on purpose -- this book's returns are
 * skewed (+1.1, from the long-put leg), and a normal-assumption VaR would
 * misstate exactly the tail that skew describes.
 */
export function valueAtRisk(returns: number[], q = 0.05): number | null {
  if (returns.length < 20) return null;
  const s = [...returns].sort((a, b) => a - b);
  const i = Math.max(0, Math.min(s.length - 1, Math.floor(q * s.length)));
  return s[i];
}

export function cagr(equity: number[], periodsPerYear = ANN): number | null {
  if (equity.length < 2 || equity[0] <= 0) return null;
  const yrs = (equity.length - 1) / periodsPerYear;
  if (yrs <= 0) return null;
  return (equity[equity.length - 1] / equity[0]) ** (1 / yrs) - 1;
}

export function totalReturn(equity: number[]): number | null {
  if (equity.length < 2 || equity[0] <= 0) return null;
  return equity[equity.length - 1] / equity[0] - 1;
}

export function calmar(equity: number[]): number | null {
  const c = cagr(equity);
  const m = maxDrawdown(equity);
  if (c === null || m === 0) return null;
  return c / Math.abs(m);
}

export function winRate(returns: number[]): number | null {
  const active = returns.filter((r) => r !== 0);
  if (!active.length) return null;
  return active.filter((r) => r > 0).length / active.length;
}

export type Stats = {
  totalReturn: number | null;
  cagr: number | null;
  maxDD: number;
  sharpe: number | null;
  sortino: number | null;
  var95: number | null;
  calmar: number | null;
  winRate: number | null;
  vol: number | null;
  nDays: number;
};

export function computeStats(equity: number[]): Stats {
  const r = toReturns(equity);
  return {
    totalReturn: totalReturn(equity),
    cagr: cagr(equity),
    maxDD: maxDrawdown(equity),
    sharpe: sharpe(r),
    sortino: sortino(r),
    var95: valueAtRisk(r, 0.05),
    calmar: calmar(equity),
    winRate: winRate(r),
    vol: r.length > 1 ? std(r) * Math.sqrt(ANN) : null,
    nDays: equity.length,
  };
}

/** Rebase a series to 100 so ours-vs-SPY is a like-for-like comparison. */
export function rebase(series: number[], base = 100): number[] {
  if (!series.length || series[0] === 0) return series.map(() => base);
  return series.map((v) => (v / series[0]) * base);
}

/** Rolling realized volatility, annualized -- the S&P vol graph in the sketch. */
export function rollingVol(returns: number[], window = 21): (number | null)[] {
  const out: (number | null)[] = [];
  for (let i = 0; i < returns.length; i++) {
    if (i < window - 1) {
      out.push(null);
      continue;
    }
    out.push(std(returns.slice(i - window + 1, i + 1)) * Math.sqrt(ANN));
  }
  return out;
}

export const fmtPct = (v: number | null, d = 2) =>
  v === null || !isFinite(v) ? "—" : `${(v * 100).toFixed(d)}%`;
export const fmtNum = (v: number | null, d = 2) =>
  v === null || !isFinite(v) ? "—" : v.toFixed(d);
export const fmtUsd = (v: number | null) =>
  v === null || !isFinite(v)
    ? "—"
    : `$${v.toLocaleString(undefined, { maximumFractionDigits: 0 })}`;
