import type { Bar } from "./heikinashi";

export type VixTermPoint = {
  t: number;             // unix seconds (shared trading-day timestamp)
  vix: number;           // VIX close (30-day)
  vix3m: number;         // VIX3M close (3-month)
  vix9d: number | null;  // VIX9D close (9-day, front of curve) — null if missing
  ratio: number;         // vix3m / vix  (>1 contango, <1 backwardation)
};

export type BackwardationRange = { startT: number; endT: number };

export type VixTermData = {
  points: VixTermPoint[];
  backwardation: BackwardationRange[];
};

// Align the VIX term structure by timestamp and derive contiguous
// backwardation date ranges. The join REQUIRES VIX and VIX3M (the pair that
// defines backwardation, strict vix3m < vix); VIX9D (front of the curve) is
// attached when present for that day and left null otherwise — a missing
// VIX9D never drops a VIX/VIX3M point. Ranges use raw affected-day timestamps;
// a one-day event has startT === endT (the chart pads bands for visibility).
export function buildVixTermStructure(
  vix: Bar[], vix3m: Bar[], vix9d: Bar[] = [],
): VixTermData {
  const v3mByT = new Map<number, number>();
  for (const b of vix3m) v3mByT.set(b.t, b.c);
  const v9dByT = new Map<number, number>();
  for (const b of vix9d) v9dByT.set(b.t, b.c);

  const points: VixTermPoint[] = [];
  for (const b of vix) {
    const v = b.c;
    const v3 = v3mByT.get(b.t);
    if (v3 === undefined) continue;      // inner join: shared VIX/VIX3M days
    if (v <= 0 || v3 <= 0) continue;     // guard divide-by-zero / bad ticks
    const v9raw = v9dByT.get(b.t);
    const v9 = v9raw !== undefined && v9raw > 0 ? v9raw : null;
    points.push({ t: b.t, vix: v, vix3m: v3, vix9d: v9, ratio: v3 / v });
  }
  points.sort((a, b) => a.t - b.t);

  const backwardation: BackwardationRange[] = [];
  let run: BackwardationRange | null = null;
  for (const p of points) {
    const inverted = p.vix3m < p.vix;    // strict: equality is contango
    if (inverted) {
      if (run) run.endT = p.t;
      else run = { startT: p.t, endT: p.t };
    } else if (run) {
      backwardation.push(run);
      run = null;
    }
  }
  if (run) backwardation.push(run);

  return { points, backwardation };
}
