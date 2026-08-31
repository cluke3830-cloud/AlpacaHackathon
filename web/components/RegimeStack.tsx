"use client";
import { useMemo } from "react";
import Plot from "./Plot";
import { C, baseLayout } from "@/lib/theme";
import { isoDay, monthlyTicks } from "@/lib/dateAxis";
import { regimeProbs } from "@/lib/hmmRegime";
import type { Bar } from "@/lib/heikinashi";

const GRN = "rgba(0,255,153,0.75)";   // calm
const GRY = "rgba(139,168,196,0.55)"; // neutral
const RED = "rgba(255,68,68,0.75)";   // volatile

// Row 3: 3-state volatility-regime probability stack (regime_v2 style).
// Filtered (causal) forward recursion runs client-side on the VIX daily bars
// the page already loads — updates live as each day's close arrives.
export default function RegimeStack({ vixBars, loading }: {
  vixBars: Bar[]; loading?: boolean;
}) {
  const fig = useMemo(() => {
    if (vixBars.length < 10) return null;
    const closes = vixBars.map((b) => b.c);
    const P = regimeProbs(closes);
    const x = vixBars.map((b) => isoDay(b.t));

    const mk = (idx: number, name: string, color: string) => ({
      type: "scatter", mode: "lines", name, x,
      y: P.map((row) => row[idx]),
      stackgroup: "one", line: { width: 0 }, fillcolor: color,
      hovertemplate: `%{x}: ${name} %{y:.0%}<extra></extra>`,
    });
    // stack order: volatile at the bottom of the legend visual? Keep calm→vol
    const traces = [mk(0, "calm", GRN), mk(1, "neutral", GRY), mk(2, "volatile", RED)];

    const ticks = monthlyTicks(vixBars.map((b) => b.t));
    const layout = baseLayout({
      height: 220,
      uirevision: "regime-stack",
      showlegend: true,
      legend: { font: { size: 9, color: C.text }, bgcolor: "rgba(5,10,20,0.7)",
                orientation: "h", x: 0, y: 1.25 },
      xaxis: { type: "category", gridcolor: C.grid, color: C.text,
               tickmode: "array", tickvals: ticks.tickvals, ticktext: ticks.ticktext },
      yaxis: { gridcolor: C.grid, color: C.text, range: [0, 1],
               tickformat: ".0%", title: { text: "P(state)", font: { size: 9 } } },
    });
    return { data: traces, layout };
  }, [vixBars]);

  if (!fig) {
    return (
      <div className="flex h-[220px] items-center justify-center text-xs text-label">
        {loading ? "loading market data…" : "no VIX data for regime stack"}
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
