"use client";
import { useMemo, useState } from "react";
import Plot from "./Plot";
import { C, SURFACE_SCALE } from "@/lib/theme";

/**
 * 3D volatility surface across an S&P 500 cross-section.
 *
 * Port of Past Strategies/Alpaca/Volatility_Surface.py: rolling realized vol
 * per symbol on a (symbol x time x vol%) surface. Two deliberate changes from
 * that script, both stated rather than silent:
 *   - universe is a SECTOR-SPREAD S&P cross-section, not a 15-name tech basket
 *     (correlated tech names give one ridge moving together; the dispersion is
 *     the whole point of the panel)
 *   - daily bars, not 1-minute — this sits on a terminal read across weeks, and
 *     daily is what the free Alpaca IEX feed serves reliably
 * Colorscale is the dashboard's own SURFACE_SCALE rather than Viridis, so it
 * matches the rest of the terminal.
 */

export type SurfaceData = {
  symbols: string[];
  dates: string[];
  z: (number | null)[][];
  window: number;
  current: Record<string, number>;
};

export default function VolSurface({ data, height = 460 }: { data: SurfaceData | null; height?: number }) {
  const [mode, setMode] = useState<"surface" | "heatmap">("surface");

  const traces = useMemo(() => {
    if (!data) return [];
    const common = {
      z: data.z, x: data.symbols, y: data.dates,
      colorscale: SURFACE_SCALE,
      colorbar: { thickness: 12, len: 0.8, title: { text: "VOL %", font: { size: 9, color: C.label } },
                  tickfont: { size: 9, color: C.label } },
      hovertemplate: "%{x} · %{y}<br>%{z:.1f}% annualized<extra></extra>",
    };
    return mode === "surface"
      ? [{ ...common, type: "surface", contours: { z: { show: true, usecolormap: true, project: { z: true } } } }]
      : [{ ...common, type: "heatmap" }];
  }, [data, mode]);

  if (!data?.symbols?.length) {
    return (
      <div className="flex items-center justify-center border border-grid text-xs text-label"
           style={{ height }}>
        no surface data — run <code className="ml-1 text-body">export_market_json.py</code>
      </div>
    );
  }

  const ranked = Object.entries(data.current).sort((a, b) => b[1] - a[1]);
  const hottest = ranked.slice(0, 3);
  const calmest = ranked.slice(-3).reverse();

  return (
    <div>
      <div className="flex flex-wrap items-center gap-2 px-1 pb-1">
        {(["surface", "heatmap"] as const).map((m) => (
          <button key={m} onClick={() => setMode(m)}
            className={`px-2 py-[2px] text-[10px] border transition-colors ${
              m === mode ? "border-cyan text-cyan" : "border-grid text-label hover:border-label"}`}>
            {m.toUpperCase()}
          </button>
        ))}
        <span className="ml-auto text-[9px] text-label">
          hottest <span className="text-neg">{hottest.map(([s, v]) => `${s} ${v.toFixed(0)}%`).join(" · ")}</span>
          {"   "}calmest <span className="text-pos">{calmest.map(([s, v]) => `${s} ${v.toFixed(0)}%`).join(" · ")}</span>
        </span>
      </div>
      <Plot
        data={traces}
        layout={{
          height,
          paper_bgcolor: C.bg, plot_bgcolor: C.bg,
          font: { family: "Courier New, monospace", color: C.text, size: 10 },
          margin: { l: 4, r: 4, t: 4, b: 4 },
          scene: {
            xaxis: { title: { text: "SYMBOL", font: { size: 9 } }, gridcolor: C.grid3d,
                     backgroundcolor: C.bg, showbackground: true, tickfont: { size: 8 } },
            yaxis: { title: { text: "DATE", font: { size: 9 } }, gridcolor: C.grid3d,
                     backgroundcolor: C.bg, showbackground: true, tickfont: { size: 8 } },
            zaxis: { title: { text: "VOL %", font: { size: 9 } }, gridcolor: C.grid3d,
                     backgroundcolor: C.bg, showbackground: true, tickfont: { size: 8 } },
            camera: { eye: { x: 1.6, y: -1.5, z: 0.85 } },
          },
          xaxis: { gridcolor: C.grid, tickfont: { size: 9, color: C.label } },
          yaxis: { gridcolor: C.grid, tickfont: { size: 9, color: C.label } },
        }}
        config={{ displayModeBar: false, responsive: true }}
        style={{ width: "100%" }}
      />
    </div>
  );
}
