import type { Bar } from "./heikinashi";
import { isoDay } from "./dateAxis";

// Regime-gated VIX mean-reversion timing signal (validated 2026-07-06, research
// vix_meanrev_timing.py). Long the index while VIX sits below its regime
// baseline; de-risk to flat when VIX SPIKES to 1.5x that baseline; re-enter when
// VIX MEAN-REVERTS back down to the baseline. "Gated by regime" = the baseline
// is a trailing 252-day mean of VIX, so "high" always means high FOR THE CURRENT
// vol regime (a fixed VIX threshold fails — post-2020 the baseline shifted up).
//
// HONEST profile (SPY, 2007-2026, causal, 2bps/switch): Sharpe 0.70 vs 0.42
// buy-hold, maxDD -27% vs -61% — a DRAWDOWN-DEFENSE overlay whose edge is
// FRONT-LOADED: Sharpe 1.26 in 2018-21 (sharp VIX-flagged crashes) but 0.48 in
// 2022+ (lags in slow grinds / fast-fade spikes). It is a discrete on/off
// version of Moreira-Muir volatility-managed portfolios — a known, published,
// replicated effect, NOT a secret edge. Shown for situational awareness.

export const MEAN_WINDOW = 252;      // trailing-year VIX mean = the regime baseline
export const MIN_PERIODS = 60;       // need >=60 obs before the mean is trustworthy
export const HI_MULT = 1.5;          // de-risk (go flat) when VIX >= baseline * HI_MULT
export const LO_MULT = 1.0;          // re-enter (go long) when VIX <= baseline * LO_MULT

export interface MeanRevSignal {
  buyDays: string[];            // isoDay of flat->long transitions (re-enter / risk-on)
  sellDays: string[];           // isoDay of long->flat transitions (de-risk / risk-off)
  position: "long" | "flat";    // current state at the most recent bar
  ready: boolean;               // enough history for the signal to be meaningful
}

// Trailing mean of the last MEAN_WINDOW closes (inclusive), or null until
// MIN_PERIODS observations exist — mirrors pandas rolling(252, min_periods=60).
function trailingMean(closes: number[], i: number): number | null {
  const start = Math.max(0, i - MEAN_WINDOW + 1);
  const n = i - start + 1;
  if (n < MIN_PERIODS) return null;
  let sum = 0;
  for (let k = start; k <= i; k++) sum += closes[k];
  return sum / n;
}

// Causal long/flat hysteresis state machine over the given VIX bars (ascending).
// Starts LONG (matches the research: position seeded to 1). Every state change
// is emitted as a BUY (flat->long) or SELL (long->flat) on the day it occurs.
// No look-ahead: day t only ever reads VIX closes <= t.
export function computeVixMeanRev(vixBars: Bar[]): MeanRevSignal {
  const bars = vixBars ?? [];
  if (bars.length < MIN_PERIODS) {
    return { buyDays: [], sellDays: [], position: "long", ready: false };
  }
  const closes = bars.map((b) => b.c);
  const buyDays: string[] = [];
  const sellDays: string[] = [];
  let isLong = true;
  for (let i = 0; i < bars.length; i++) {
    const mean = trailingMean(closes, i);
    if (mean == null) continue;               // warmup — stay long, emit nothing
    const v = closes[i];
    if (isLong && v >= mean * HI_MULT) {
      isLong = false;
      sellDays.push(isoDay(bars[i].t));
    } else if (!isLong && v <= mean * LO_MULT) {
      isLong = true;
      buyDays.push(isoDay(bars[i].t));
    }
  }
  return {
    buyDays, sellDays,
    position: isLong ? "long" : "flat",
    ready: true,
  };
}
