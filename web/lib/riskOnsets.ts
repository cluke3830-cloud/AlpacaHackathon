import type { Bar } from "./heikinashi";
import { isoDay } from "./dateAxis";

// Signal-onset dots for the elevated-risk gate (short-γ & VIX>=20): the exact
// day the gate FIRES after being quiet, scored by what actually happened next.
// No hindsight selection — every onset is shown, hit or miss, and recent onsets
// whose outcome window hasn't closed yet are PENDING (they resolve live as new
// daily bars arrive). Honest by construction: the ~17% hit rate is visible.

export type OnsetOutcome = "crisis" | "hit" | "miss" | "pending";

export interface RiskOnset {
  day: string;        // isoDay of the onset (first flagged day of a run)
  idx: number;        // index into the bars array
  outcome: OnsetOutcome;
  strong: boolean;    // full mechanism stack aligned at fire time (see below)
}

// Outcome window: 20 trading days (~1 month). The 10d window clipped slow-grind
// declines (Oct-2018, Mar-2026 fired at the top but bottomed on day 17-20 →
// phantom "misses"). Two hit tiers (TC's crisis framing, both validated):
//   DIP    >= 5%  — 30.7% of fires vs 18.5% base = 1.7x (markets do 5% naturally)
//   CRISIS >= 10% — 9.1% of fires vs 4.0% base = 2.2x, OOS 9/9 (the balanced
//   best; catch list = Dec-2018, COVID, 4x 2022 legs, Mar-2025)
const RESOLVE_BARS = 20;
const DIP_PCT = -0.05;
const CRISIS_PCT = -0.10;

// bars: daily bars ascending; riskDays: the merged flagged-day set.
// Onset = a flagged bar whose PREVIOUS bar (previous trading day) is unflagged
// (or is the first bar). Outcome from the onset CLOSE: hit if the min close of
// the next 1..RESOLVE_BARS bars is <= DROP_PCT below it; pending while the
// window is still open and no hit yet; miss once the full window passed.
// strongDays (optional): days where the FULL mechanism stack was aligned —
// short-γ & VIX>=22 & VIX9D>VIX (front inverted) & spot below the gamma flip.
// Onsets on those days hit 37.5% (OOS 38%/38%) vs 30.7% baseline.
export function buildRiskOnsets(
  bars: Bar[], riskDays: Set<string>, strongDays?: Set<string>,
): RiskOnset[] {
  const out: RiskOnset[] = [];
  for (let i = 0; i < bars.length; i++) {
    const d = isoDay(bars[i].t);
    if (!riskDays.has(d)) continue;
    if (i > 0 && riskDays.has(isoDay(bars[i - 1].t))) continue;  // run continues
    const c0 = bars[i].c;
    const end = Math.min(bars.length - 1, i + RESOLVE_BARS);
    let maxDrop = 0;
    for (let j = i + 1; j <= end; j++) {
      maxDrop = Math.min(maxDrop, bars[j].c / c0 - 1);
    }
    // Tiering recomputes on every render, so a live "hit" upgrades to "crisis"
    // automatically if the drop deepens while the window is still open.
    let outcome: OnsetOutcome;
    if (maxDrop <= CRISIS_PCT) outcome = "crisis";
    else if (maxDrop <= DIP_PCT) outcome = "hit";
    else if (i + RESOLVE_BARS > bars.length - 1) outcome = "pending";
    else outcome = "miss";        // full window elapsed, no qualifying drop
    out.push({ day: d, idx: i, outcome, strong: strongDays?.has(d) ?? false });
  }
  return out;
}
