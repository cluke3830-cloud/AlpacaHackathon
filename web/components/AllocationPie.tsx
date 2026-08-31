"use client";
import Plot from "./Plot";
import { CONFIG, C } from "@/lib/plotTheme";

/** Long / Short / Cash donut — the circle in the sketch. */
export default function AllocationPie({
  long, short, cash, height = 210,
}: { long: number; short: number; cash: number; height?: number }) {
  const total = long + short + cash;
  if (total <= 0) {
    return (
      <div className="flex h-[210px] items-center justify-center border border-grid text-xs text-label">
        no allocation data
      </div>
    );
  }
  return (
    <Plot
      data={[{
        type: "pie", hole: 0.55,
        labels: ["LONG", "SHORT", "CASH"],
        values: [long, short, cash],
        marker: { colors: [C.pos, C.neg, C.label], line: { color: "#050A14", width: 2 } },
        textinfo: "label+percent",
        textfont: { size: 10, family: "Courier New, monospace", color: "#050A14" },
        hovertemplate: "%{label}: $%{value:,.0f} (%{percent})<extra></extra>",
        sort: false,
      }]}
      layout={{
        height,
        paper_bgcolor: "rgba(0,0,0,0)",
        plot_bgcolor: "rgba(0,0,0,0)",
        margin: { l: 8, r: 8, t: 8, b: 8 },
        showlegend: false,
        font: { family: "Courier New, monospace", color: "#8BA8C4", size: 10 },
      }}
      config={CONFIG}
      style={{ width: "100%" }}
    />
  );
}
