// Per-strike dealer gamma-exposure profile — the "many small blocks" view.
//
// The relay already hands us a full signed GEX-by-strike array
// (calls +, puts −, weighted gamma·OI·100·S — see relay/aggregates.py). This
// module shapes it for the GammaProfile panel: window it around spot so the
// bars stay dense and readable, find the call/put walls, carry the flip line,
// and derive the ±1σ band from the chain's expected move. Pure + testable so
// the Plotly component stays a thin renderer.

export type GammaChain = {
  spot: number;
  expected_move?: number | null;
  gamma_flip?: number | null;
  gex_profile: { strike: number; gex: number }[];
} | null;

export type GammaBar = { strike: number; gex: number; sign: 1 | -1 };

export type GammaProfile = {
  bars: GammaBar[];                 // sorted ascending by strike, windowed, nonzero
  netGex: number;                   // summed over the windowed bars
  flip: number | null;              // gamma-flip strike (from full-chain relay calc)
  spot: number;
  callWall: number | null;          // strike of the largest +GEX (price magnet above)
  putWall: number | null;           // strike of the most -GEX (accelerant below)
  sigmaBand: [number, number] | null; // [spot − EM, spot + EM]
  clusters: number[];               // top-K |GEX| strikes (dealer concentration)
  maxAbsGex: number;                // largest |GEX| in the window (bar scaling)
};

export type GammaOpts = {
  windowPct?: number;  // keep strikes within ±this fraction of spot (default 0.15)
  clusterK?: number;   // how many top-|GEX| strikes to flag (default 5)
};

export function buildGammaProfile(
  chain: GammaChain,
  opts: GammaOpts = {},
): GammaProfile | null {
  if (!chain || !chain.gex_profile?.length) return null;
  const { windowPct = 0.15, clusterK = 5 } = opts;
  const spot = chain.spot;

  // Window around spot and drop dead (zero-GEX) strikes so we render a tight
  // cluster of meaningful bars instead of a sea of empty far-OTM rows.
  const lo = spot * (1 - windowPct);
  const hi = spot * (1 + windowPct);
  const bars: GammaBar[] = chain.gex_profile
    .filter((p) => p.gex !== 0 && p.strike >= lo && p.strike <= hi)
    .map((p) => ({ strike: p.strike, gex: p.gex, sign: (p.gex >= 0 ? 1 : -1) as 1 | -1 }))
    .sort((a, b) => a.strike - b.strike);

  if (!bars.length) return null;

  const netGex = bars.reduce((a, b) => a + b.gex, 0);
  const maxAbsGex = Math.max(...bars.map((b) => Math.abs(b.gex)));

  // Walls: the single biggest magnet above (max +GEX) and accelerant below
  // (most −GEX). Computed over the windowed bars so they track the live action.
  let callWall: number | null = null, putWall: number | null = null;
  let maxPos = 0, minNeg = 0;
  for (const b of bars) {
    if (b.gex > maxPos) { maxPos = b.gex; callWall = b.strike; }
    if (b.gex < minNeg) { minNeg = b.gex; putWall = b.strike; }
  }

  const em = chain.expected_move ?? 0;
  const sigmaBand: [number, number] | null =
    em > 0 ? [spot - em, spot + em] : null;

  const clusters = [...bars]
    .sort((a, b) => Math.abs(b.gex) - Math.abs(a.gex))
    .slice(0, clusterK)
    .map((b) => b.strike);

  return {
    bars,
    netGex,
    flip: chain.gamma_flip ?? null,
    spot,
    callWall,
    putWall,
    sigmaBand,
    clusters,
    maxAbsGex,
  };
}
