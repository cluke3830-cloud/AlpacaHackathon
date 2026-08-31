"use client";
import { useMemo } from "react";
import Plot from "./Plot";
import { C, baseLayout } from "@/lib/theme";
import { isoDay, monthlyTicks } from "@/lib/dateAxis";
import type { VixTermData } from "@/lib/vixTermStructure";

export default function VixTermChart({ data, loading }: {
  data: VixTermData; loading?: boolean;
}) {
  const fig = useMemo(() => {
    if (!data.points.length) return null;
    // Gapless categorical x: one evenly-spaced slot per trading day (avoids the
    // date-axis + weekend-rangebreak clipping that fragmented the lines in ET).
    const x = data.points.map((p) => isoDay(p.t));
    const idxByT = new Map(data.points.map((p, i) => [p.t, i]));

    // Term structure front → back: VIX9D (9d, gold) leads the inversion, then
    // VIX (30d, red), then VIX3M (3m, cyan). VIX9D uses null gaps for any day
    // it's missing so the line simply breaks rather than dropping to zero.
    const traces = [
      { type: "scatter", mode: "lines", name: "VIX9D",
        x, y: data.points.map((p) => p.vix9d),
        connectgaps: false, line: { color: C.gold, width: 1.25 } },
      { type: "scatter", mode: "lines", name: "VIX",
        x, y: data.points.map((p) => p.vix),
        line: { color: C.neg, width: 1.5 } },
      { type: "scatter", mode: "lines", name: "VIX3M",
        x, y: data.points.map((p) => p.vix3m),
        line: { color: C.cyan, width: 1.5 } },
    ];

    // Backwardation (VIX3M < VIX) bands, drawn behind the lines. On a category
    // axis, positions are category indices; ±0.5 pads the band around its days
    // so a one-day event is still visible.
    const shapes = data.backwardation.map((r) => ({
      type: "rect", xref: "x", yref: "paper",
      x0: (idxByT.get(r.startT) ?? 0) - 0.5,
      x1: (idxByT.get(r.endT) ?? 0) + 0.5,
      y0: 0, y1: 1,
      fillcolor: "rgba(255,68,68,0.14)", line: { width: 0 }, layer: "below",
    }));

    const ticks = monthlyTicks(data.points.map((p) => p.t));
    const layout = baseLayout({
      height: 300,
      uirevision: "vixterm",
      showlegend: true,
      legend: { font: { size: 9, color: C.text }, bgcolor: "rgba(5,10,20,0.7)",
                orientation: "h", x: 0, y: 1.08 },
      xaxis: { type: "category", gridcolor: C.grid, color: C.text,
               tickmode: "array", tickvals: ticks.tickvals, ticktext: ticks.ticktext },
      yaxis: { gridcolor: C.grid, color: C.text, title: { text: "vol", font: { size: 9 } } },
      shapes,
    });
    return { data: traces, layout };
  }, [data]);

  if (!fig) {
    return (
      <div className="flex h-[300px] items-center justify-center text-xs text-label">
        {loading ? "loading market data…" : "no VIX / VIX3M data"}
      </div>
    );
  }
  return (
    <div className={loading ? "opacity-40 transition-opacity" : "transition-opacity"}>
      <Plot data={fig.data as never} layout={fig.layout as never}
        config={{ displayModeBar: false, scrollZoom: false }}
        style={{ width: "100%" }} useResizeHandler />
    </div>
  );
}
