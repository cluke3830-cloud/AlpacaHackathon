// Dealer-gamma risk read — an HONEST risk-context signal, not a crash predictor.
// Net GEX here is the same Σ(call γ·OI − put γ·OI) the relay computes (gex_profile),
// same sign as the validated 2018-2026 backtest:
//   net GEX >= 0  -> dealers LONG gamma  -> PINNED   (hedging dampens moves)
//   net GEX <  0  -> dealers SHORT gamma -> TRAPDOOR (hedging amplifies moves)
//
// ELEVATED RISK = short gamma AND VIX >= stress line (default 20). A VIX-level
// sweep (2018-2026) showed danger concentrates at HIGH VIX, and short-gamma adds
// a robust ~+2pt precision bump on top: short-γ & VIX>=20 hits a >=5% drop within
// 10d ~17% of the time = 2.0x the 8.5% base, gamma>VIX-alone 9/9 years + both OOS
// halves. Still 83% no-drop -> an elevated-risk flag, NOT a forecast. (The earlier
// "hidden fragility in CALM markets" gate was below the base rate — calm days are
// safer — so it was dropped.)

export type GammaRegime = "pinned" | "trapdoor";

export interface FragilityRead {
  netGex: number;
  regime: GammaRegime;
  vix: number | null;
  stressed: boolean;       // vix >= stressVix
  elevatedRisk: boolean;   // trapdoor AND stressed = short gamma into stress (2x drop risk)
}

// stressVix default 20 = the sweep's sweet spot (17-18% precision, 2.0x lift).
export function readFragility(
  netGex: number, vix: number | null, stressVix = 20,
): FragilityRead {
  const regime: GammaRegime = netGex >= 0 ? "pinned" : "trapdoor";
  const stressed = vix != null && vix >= stressVix;
  return { netGex, regime, vix, stressed, elevatedRisk: regime === "trapdoor" && stressed };
}
