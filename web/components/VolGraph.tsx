"use client";
import { useMemo } from "react";
import Plot from "./Plot";
import { LAYOUT, CONFIG, C } from "@/lib/plotTheme";
import { toReturns, rollingVol } from "@/lib/stats";

/**
 * Realized volatility of the S&P (SPY), 21d rolling annualized.
 *
 * REALIZED, not implied, and labeled as such: VIX is not available on Alpaca
 * (`^VIX` is not a tradeable symbol there, and VIXY/VXX are decaying roll ETFs
 * whose level is not a vol reading). Substituting one for the other is an
 * anti-pattern this fund has an explicit rule against, so the panel shows what
 * the data source can honestly support.
 */
export default function VolGraph({
  times, closes, height = 200,
}: { times: string[]; closes: number[]; height?: number }) {
  const { x, y } = useMemo(() => {
    const r = toReturns(closes);
    const v = rollingVol(r, 21);
    return { x: times.slice(1), y: v };
  }, [times, closes]);

  if (!closes.length) {
    return (
      <div className="flex h-[200px] items-center justify-center border border-grid text-xs text-label">
        no SPY history
      </div>
    );
  }

  return (
    <Plot
      data={[{
        x, y, type: "scatter", mode: "lines",
        line: { color: C.gold, width: 1.4 },
        fill: "tozeroy", fillcolor: "rgba(255,215,0,0.08)",
        name: "SPY 21d RV",
        hovertemplate: "%{y:.1%}<extra>21d realized vol</extra>",
      }]}
      layout={{
        ...LAYOUT, height, showlegend: false,
        margin: { l: 46, r: 12, t: 8, b: 28 },
        yaxis: { ...LAYOUT.yaxis, tickformat: ".0%" },
      }}
      config={CONFIG}
      style={{ width: "100%" }}
    />
  );
}
