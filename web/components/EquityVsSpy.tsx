"use client";
import { useMemo } from "react";
import Plot from "./Plot";
import { LAYOUT, CONFIG, C } from "@/lib/plotTheme";
import { rebase } from "@/lib/stats";

export type ChartKind = "line" | "area";

/**
 * Ours (red) vs SPY (blue), both rebased to 100.
 *
 * REBASING IS NOT COSMETIC: the account is ~$100k and SPY is ~$765, so on raw
 * axes one line is a flat floor under the other and the comparison -- the
 * entire point of the panel -- is unreadable. Rebasing to a common 100 makes
 * the two directly comparable in percentage terms.
 */
export default function EquityVsSpy({
  times, ours, spy, kind = "line", height = 380,
}: {
  times: string[];
  ours: number[];
  spy: number[] | null;
  kind?: ChartKind;
  height?: number;
}) {
  const traces = useMemo(() => {
    const o = rebase(ours);
    const t: any[] = [
      {
        x: times, y: o, type: "scatter", mode: "lines", name: "OURS",
        line: { color: C.ours, width: 2 },
        fill: kind === "area" ? "tozeroy" : undefined,
        fillcolor: kind === "area" ? "rgba(255,68,68,0.10)" : undefined,
        hovertemplate: "%{y:.2f}<extra>OURS</extra>",
      },
    ];
    if (spy && spy.length) {
      t.push({
        x: times.slice(0, spy.length), y: rebase(spy),
        type: "scatter", mode: "lines", name: "SPY",
        line: { color: C.spy, width: 1.6 },
        hovertemplate: "%{y:.2f}<extra>SPY</extra>",
      });
    }
    return t;
  }, [times, ours, spy, kind]);

  if (!ours.length) {
    return (
      <div className="flex h-[380px] items-center justify-center border border-grid text-xs text-label">
        no equity history yet — the account has not traded
      </div>
    );
  }

  return (
    <Plot
      data={traces}
      layout={{
        ...LAYOUT, height,
        yaxis: { ...LAYOUT.yaxis, title: { text: "INDEXED = 100", font: { size: 9, color: C.label } } },
      }}
      config={CONFIG}
      style={{ width: "100%" }}
    />
  );
}
