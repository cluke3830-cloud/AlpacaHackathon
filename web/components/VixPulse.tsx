"use client";
import { C } from "@/lib/theme";

/**
 * VIX level + 1-day change, as a header pulse.
 *
 * OptionDashboard's version polls its relay for intraday VIX. Here the value
 * comes from the daily CBOE archive via market.json, so it is a DAILY close,
 * not an intraday tick -- labeled with its as-of date rather than implying a
 * liveness the source does not have.
 */
export default function VixPulse({ vix, prev, asOf }: {
  vix: number | null; prev: number | null; asOf?: string;
}) {
  if (vix == null) {
    return (
      <div className="flex items-center gap-2 text-xs text-label">
        <span className="uppercase tracking-[0.06em]">VIX</span>
        <span className="text-dim">…</span>
      </div>
    );
  }
  const chg = prev != null ? vix - prev : null;
  const tone = vix >= 25 ? C.neg : vix >= 20 ? C.gold : C.pos;
  return (
    <div className="flex items-center gap-2 text-xs">
      <span className="uppercase tracking-[0.06em] text-label">VIX</span>
      <span className="font-bold tabular-nums" style={{ color: tone }}>{vix.toFixed(2)}</span>
      {chg != null && (
        <span className="tabular-nums" style={{ color: chg >= 0 ? C.neg : C.pos }}>
          {chg >= 0 ? "▲" : "▼"}{Math.abs(chg).toFixed(2)}
        </span>
      )}
      {asOf && <span className="text-[9px] text-dim">{asOf}</span>}
    </div>
  );
}
