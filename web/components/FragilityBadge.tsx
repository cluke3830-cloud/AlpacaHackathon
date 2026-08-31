"use client";
import { C } from "@/lib/theme";
import type { FragilityRead } from "@/lib/gammaRegime";

// Dealer-gamma regime badge — honest risk context (live SPY net GEX sign), NOT a
// traded signal. ELEVATED RISK (short gamma AND VIX >= 20) is the gate the VIX
// sweep validated: ~17% >=5%-drop-in-10d (2.0x base), gamma beats VIX-alone 9/9
// years + both OOS halves — still ~83% no-drop, so a risk flag, not a forecast.
export default function FragilityBadge({ read }: { read: FragilityRead | null }) {
  if (!read) {
    return (
      <div className="flex items-center gap-2 text-xs text-label">
        <span className="uppercase tracking-[0.06em]">Gamma</span>
        <span className="text-dim">…</span>
      </div>
    );
  }
  const ui = read.elevatedRisk
    ? { txt: "⚠ ELEVATED RISK", color: C.gold }
    : read.regime === "trapdoor"
      ? { txt: "TRAPDOOR", color: C.neg }
      : { txt: "PINNED", color: C.pos };
  const b = read.netGex / 1e9;
  return (
    <div className="flex items-center gap-2 text-xs"
      title="Dealer-gamma regime from live SPY net GEX. TRAPDOOR (short γ) = hedging amplifies moves; PINNED (long γ) = dampens. ELEVATED RISK = short γ AND VIX >= 20 (~2x elevated drop risk, not a forecast).">
      <span className="uppercase tracking-[0.06em] text-label">Gamma</span>
      <span className="tabular-nums text-label">net {b >= 0 ? "+" : "−"}${Math.abs(b).toFixed(1)}B</span>
      <span className="border px-1.5 py-0.5 font-bold tracking-[0.04em]"
        style={{ color: ui.color, borderColor: ui.color }}>
        {ui.txt}
      </span>
    </div>
  );
}
