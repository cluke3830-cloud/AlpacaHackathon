// 3-state volatility-regime NOWCAST (calm / neutral / volatile) — the Row-3
// context layer. A 2018-2026 walk-forward Gaussian HMM on log(VIX) validated
// the object (stable state means ≈ VIX 12.8 / 17.2 / 25.7 across 9 annual
// refits); these params are the fit through 2025-12-31, so filtering 2026+
// closes is causal. The browser runs the same FORWARD (filtered) recursion —
// P(state_t | data ≤ t) — live on the VIX bars the page already loads.
//
// HONEST FRAME: this is context ("where are we"), NOT a signal — switching the
// fire-gate's VIX threshold on regimes was tested 3x (proxy, 2-state, 3-state)
// and retired every time (crash-starts live INSIDE the volatile regime).
// Refit note: refresh these params annually (script: research/vix_drawdown/
// hmm3_regime.py exports hmm3_params.json).

export type RegimeState = "calm" | "neutral" | "volatile";
export const REGIME_LABELS: RegimeState[] = ["calm", "neutral", "volatile"];

// GaussianHMM(log VIX), states ordered by mean. Fitted 2012-01..2025-12-31.
const START = [0, 0, 1];                      // (numerically ~exact from fit)
const TRANS = [
  [0.9738538079204507, 0.026143395924595005, 2.7961549542774125e-06],
  [0.02915564147202715, 0.949757986920808, 0.02108637160716483],
  [1.5996809606993876e-21, 0.03422390435169402, 0.965776095648306],
];
const MEANS = [2.551719013573319, 2.8449547429197635, 3.2475636809757735];
const VARS  = [0.012879651315526626, 0.010368436173905158, 0.05118865165708447];

// State means back in VIX points (for labels/tooltips): ~[12.8, 17.2, 25.7]
export const REGIME_VIX_MEANS = MEANS.map((m) => Math.exp(m));

function gaussPdf(x: number, mu: number, v: number): number {
  return Math.exp(-0.5 * (x - mu) * (x - mu) / v) / Math.sqrt(2 * Math.PI * v);
}

// Forward-filtered P(state) for each day, given ascending VIX closes.
// Row t uses only closes[0..t] — causal by construction.
export function regimeProbs(vixCloses: number[]): number[][] {
  const n = vixCloses.length;
  if (n === 0) return [];
  const out: number[][] = [];
  let a = [0, 0, 0];
  for (let j = 0; j < 3; j++) {
    a[j] = START[j] * gaussPdf(Math.log(vixCloses[0]), MEANS[j], VARS[j]);
  }
  let s = a[0] + a[1] + a[2] || 1;
  a = a.map((v) => v / s);
  out.push([...a]);
  for (let t = 1; t < n; t++) {
    const lx = Math.log(vixCloses[t]);
    const next = [0, 0, 0];
    for (let j = 0; j < 3; j++) {
      const pred = a[0] * TRANS[0][j] + a[1] * TRANS[1][j] + a[2] * TRANS[2][j];
      next[j] = pred * gaussPdf(lx, MEANS[j], VARS[j]);
    }
    s = next[0] + next[1] + next[2];
    a = s > 0 ? next.map((v) => v / s) : [1 / 3, 1 / 3, 1 / 3];
    out.push([...a]);
  }
  return out;
}

export function currentRegime(probs: number[][]): { state: RegimeState; p: number } | null {
  if (!probs.length) return null;
  const last = probs[probs.length - 1];
  let k = 0;
  for (let j = 1; j < 3; j++) if (last[j] > last[k]) k = j;
  return { state: REGIME_LABELS[k], p: last[k] };
}
