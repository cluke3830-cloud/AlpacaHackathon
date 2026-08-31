"use client";
import { useMemo, useState } from "react";
import type { Order } from "@/lib/alpaca";

const WINDOWS = ["1M", "3M", "6M", "1Y", "2Y", "3Y", "ALL"] as const;
export type TradeWindow = (typeof WINDOWS)[number];

const DAYS: Record<TradeWindow, number> = {
  "1M": 30, "3M": 91, "6M": 182, "1Y": 365, "2Y": 730, "3Y": 1095, ALL: 1e6,
};

/** OCC symbols are unreadable raw: SPY260904C00760000 -> SPY 09/04 760C */
function prettyOcc(sym: string): string {
  const m = /^([A-Z]+)(\d{2})(\d{2})(\d{2})([CP])(\d{8})$/.exec(sym);
  if (!m) return sym;
  const [, root, , mm, dd, cp, strike] = m;
  return `${root} ${mm}/${dd} ${(Number(strike) / 1000).toFixed(0)}${cp}`;
}

export default function TradeLog({ trades }: { trades: Order[] }) {
  const [win, setWin] = useState<TradeWindow>("3M");

  const rows = useMemo(() => {
    const cut = Date.now() - DAYS[win] * 864e5;
    return trades
      .filter((t) => new Date(t.filled_at ?? t.submitted_at).getTime() >= cut)
      .sort(
        (a, b) =>
          new Date(b.filled_at ?? b.submitted_at).getTime() -
          new Date(a.filled_at ?? a.submitted_at).getTime()
      );
  }, [trades, win]);

  const notional = rows.reduce(
    (a, t) => a + t.filled_qty * (t.filled_avg_price ?? 0) * (t.asset_class === "us_option" ? 100 : 1),
    0
  );

  return (
    <div className="border border-grid bg-panel/40">
      <div className="flex flex-wrap items-center gap-2 border-b border-grid px-3 py-2">
        <span className="text-[11px] tracking-[0.14em] text-cyan">TRADEBOOK</span>
        <div className="flex gap-1">
          {WINDOWS.map((w) => (
            <button
              key={w}
              onClick={() => setWin(w)}
              className={`px-2 py-[2px] text-[10px] border transition-colors ${
                w === win ? "border-cyan text-cyan" : "border-grid text-label hover:border-label"
              }`}
            >
              {w}
            </button>
          ))}
        </div>
        <span className="ml-auto text-[10px] text-label">
          {rows.length} fills · ${notional.toLocaleString(undefined, { maximumFractionDigits: 0 })} notional
        </span>
      </div>

      {rows.length === 0 ? (
        <div className="px-3 py-6 text-center text-xs text-label">
          no fills in this window
        </div>
      ) : (
        <div className="max-h-[300px] overflow-y-auto">
          <table className="w-full text-[11px]">
            <thead className="sticky top-0 bg-[#081524] text-[9px] tracking-[0.08em] text-label">
              <tr>
                <th className="px-3 py-1 text-left font-normal">FILLED</th>
                <th className="px-2 py-1 text-left font-normal">SYMBOL</th>
                <th className="px-2 py-1 text-left font-normal">SIDE</th>
                <th className="px-2 py-1 text-right font-normal">QTY</th>
                <th className="px-2 py-1 text-right font-normal">PRICE</th>
                <th className="px-3 py-1 text-right font-normal">NOTIONAL</th>
              </tr>
            </thead>
            <tbody className="tabular-nums">
              {rows.map((t, i) => {
                const mult = t.asset_class === "us_option" ? 100 : 1;
                const px = t.filled_avg_price ?? 0;
                const buy = t.side === "buy";
                return (
                  <tr key={i} className="border-t border-grid/40 hover:bg-[#0A1626]">
                    <td className="px-3 py-1 text-label">
                      {new Date(t.filled_at ?? t.submitted_at).toLocaleString(undefined, {
                        month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit",
                      })}
                    </td>
                    <td className="px-2 py-1">{prettyOcc(t.symbol)}</td>
                    <td className={`px-2 py-1 ${buy ? "text-pos" : "text-neg"}`}>
                      {t.side.toUpperCase()}
                    </td>
                    <td className="px-2 py-1 text-right">{t.filled_qty}</td>
                    <td className="px-2 py-1 text-right">${px.toFixed(2)}</td>
                    <td className="px-3 py-1 text-right text-label">
                      ${(t.filled_qty * px * mult).toLocaleString(undefined, { maximumFractionDigits: 0 })}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
