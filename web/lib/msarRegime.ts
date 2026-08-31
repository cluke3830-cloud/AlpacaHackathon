import type { Bar } from "./heikinashi";
import { isoDay } from "./dateAxis";

// 2-regime Markov-Switching AR(1) on log(VIX) — the "regime-switching Heston
// cousin" timing signal (validated 2026-07-10, research msar2_signal_test.py:
// SPY Sharpe 1.01 vs deployed-SMA 0.90 vs B&H 0.69 on the 2016-2026 causal
// window; maxDD -18% vs -27%; beat both sub-periods; all 3 threshold pairs
// beat SMA; edge survives excl-2020 and costs to ~10bp/switch).
//
// Model (statsmodels MarkovAutoregression mean-adjusted form):
//   (y_t - mu[s_t]) = ar[s_t] * (y_{t-1} - mu[s_{t-1}]) + eps,  eps~N(0, sigma2[s_t])
// The conditional density depends on BOTH s_t and s_{t-1}, so the Hamilton
// filter must run over the joint (s_t, s_{t-1}) — marginalizing after, not
// before. Port verified against statsmodels' own .filter() output (golden
// vectors in __tests__/msarRegime.test.ts) — do not "simplify" the joint
// filter to a marginal one; it changes the numbers.
//
// REFIT ANNUALLY (like hmmRegime.ts): rerun research/vix_drawdown/
// export_msar_params.py each January, update MSAR_PARAMS + goldens.
// Fitted through 2025-12-31 on FMP ^VIX closes since 2005.

export const MSAR_PARAMS = {
  // transition probabilities: p00 = P(next=0 | cur=0), p10 = P(next=0 | cur=1)
  p00: 0.9435572465597281,
  p10: 0.18708137699061436,
  mu: [2.665002351420495, 2.7435264278798406],      // regime means of log(VIX)
  ar: [0.980322651822494, 0.9952075033352669],      // regime AR coefs (reversion speed)
  sigma2: [0.002211934389264514, 0.014770515316871608],
  hiState: 1,                                        // high-vol regime = larger sigma2
} as const;

// Hysteresis thresholds on filtered P(high-vol) — the middle of the three
// pre-registered pairs (0.9/0.5, 0.7/0.3, 0.5/0.2), all of which beat SMA.
export const SELL_P = 0.7;
export const BUY_P = 0.3;
export const MIN_BARS = 30;   // need some history before the filter is meaningful

function normPdf(x: number, mean: number, variance: number): number {
  return Math.exp(-0.5 * (x - mean) * (x - mean) / variance) /
         Math.sqrt(2 * Math.PI * variance);
}

// Filtered P(high-vol regime | closes[0..t]) for every t >= 1, via the
// Hamilton filter over the joint (s_t, s_{t-1}). closes = raw VIX (not log).
// Initial state distribution: uniform (statsmodels default for .filter()
// uses steady-state; uniform converges to the same filtered path within a
// few observations — parity verified on the golden window despite this).
export function msarFilteredProbs(closes: number[]): number[] {
  const { p00, p10, mu, ar, sigma2, hiState } = MSAR_PARAMS;
  const A = [[p00, 1 - p00], [p10, 1 - p10]];   // A[i][j] = P(s_t=j | s_{t-1}=i)
  const y = closes.map(Math.log);
  const n = y.length;
  const out: number[] = new Array(n).fill(NaN);
  if (n < 2) return out;
  let filt = [0.5, 0.5];                         // P(s_{t-1} | info_{t-1})
  for (let t = 1; t < n; t++) {
    // joint predicted x conditional density, over (i = s_{t-1}, j = s_t)
    let total = 0;
    const jointNew = [0, 0];                     // marginal over s_t after summing i
    for (let i = 0; i < 2; i++) {
      for (let j = 0; j < 2; j++) {
        const mean = mu[j] + ar[j] * (y[t - 1] - mu[i]);
        const w = filt[i] * A[i][j] * normPdf(y[t], mean, sigma2[j]);
        jointNew[j] += w;
        total += w;
      }
    }
    if (total > 0) {
      filt = [jointNew[0] / total, jointNew[1] / total];
    } else {
      filt = [0.5, 0.5];                         // numerical dead-end: reset
    }
    out[t] = filt[hiState];
  }
  return out;
}

export interface MsarSignal {
  buyDays: string[];            // isoDay of flat->long transitions (re-enter)
  sellDays: string[];           // isoDay of long->flat transitions (de-risk)
  position: "long" | "flat";
  pHigh: number | null;         // latest filtered P(high-vol)
  ready: boolean;
}

// Causal long/flat hysteresis on the filtered P(high-vol): SELL when
// P >= 0.7, BUY back when P <= 0.3. Starts long (matches the research).
export function computeMsarSignal(vixBars: Bar[]): MsarSignal {
  const bars = vixBars ?? [];
  if (bars.length < MIN_BARS) {
    return { buyDays: [], sellDays: [], position: "long", pHigh: null, ready: false };
  }
  const probs = msarFilteredProbs(bars.map((b) => b.c));
  const buyDays: string[] = [];
  const sellDays: string[] = [];
  let isLong = true;
  for (let i = 0; i < bars.length; i++) {
    const p = probs[i];
    if (Number.isNaN(p)) continue;
    if (isLong && p >= SELL_P) {
      isLong = false;
      sellDays.push(isoDay(bars[i].t));
    } else if (!isLong && p <= BUY_P) {
      isLong = true;
      buyDays.push(isoDay(bars[i].t));
    }
  }
  const last = probs[probs.length - 1];
  return {
    buyDays, sellDays,
    position: isLong ? "long" : "flat",
    pHigh: Number.isNaN(last) ? null : last,
    ready: true,
  };
}
