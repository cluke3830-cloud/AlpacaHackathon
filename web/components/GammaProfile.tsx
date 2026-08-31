"use client";
import { useMemo } from "react";
import Plot from "./Plot";
import { C, baseLayout } from "@/lib/theme";
import { buildGammaProfile, type GammaChain } from "@/lib/gammaProfile";

// Full-width per-strike dealer gamma profile — "many small blocks". Each strike
// is one thin horizontal bar (green = dealers long gamma / price magnet,
// red = short gamma / accelerant). Overlaid: the γ-flip line, spot, the ±1σ
// expected-move band, and call/put-wall markers. Replaces the cramped right-
// edge GEX strip with a proper standalone panel.

const HEIGHT = 460;

// U.S. options RTH, in the user's local clock (= ET for this desk).
function marketIsOpen(): boolean {
  const now = new Date();
  const day = now.getDay();
  if (day === 0 || day === 6) return false;          // weekend
  const mins = now.getHours() * 60 + now.getMinutes();
  return mins >= 9 * 60 + 30 && mins < 16 * 60;       // 09:30–16:00 ET
}

function chip(label: string, value: string, color: string) {
  return (
    <div key={label} className="border border-grid bg-[#0A1628] px-3 py-1.5">
      <div className="text-[9px] tracking-[0.08em] text-label">{label}</div>
      <div className="text-sm leading-tight" style={{ color }}>{value}</div>
    </div>
  );
}

export default function GammaProfile({ chain }: { chain: GammaChain }) {
  const model = useMemo(() => buildGammaProfile(chain), [chain]);

  const fig = useMemo(() => {
    if (!model) return null;
    const { bars, spot, flip, sigmaBand, clusters, maxAbsGex } = model;
    const clusterSet = new Set(clusters);

    // Bar thickness in price units: ~80% of the tightest strike gap so dense
    // grids (1-pt SPY strikes) and coarse ones (5-pt index strikes) both read
    // as discrete blocks without overlapping.
    let gap = Infinity;
    for (let i = 1; i < bars.length; i++)
      gap = Math.min(gap, bars[i].strike - bars[i - 1].strike);
    if (!isFinite(gap) || gap <= 0) gap = 1;
    const width = gap * 0.8;

    const strikes = bars.map((b) => b.strike);
    const xs = bars.map((b) => b.gex / 1e6);              // $M
    const colors = bars.map((b) => (b.sign > 0 ? C.pos : C.neg));
    // Dealer-concentration strikes pop at full opacity; the rest sit muted, so
    // the walls stand out by brightness while keeping their true green/red.
    const opacity = bars.map((b) => (clusterSet.has(b.strike) ? 1 : 0.4));

    const data: object[] = [
      {
        type: "bar", orientation: "h", x: xs, y: strikes, width,
        marker: { color: colors, opacity },
        hovertemplate: "Strike $%{y}<br>GEX %{x:.1f}M<extra></extra>",
        showlegend: false,
      },
    ];

    const yLo = Math.min(...strikes, spot) - gap;
    const yHi = Math.max(...strikes, spot) + gap;

    const shapes: object[] = [];
    const annotations: object[] = [];

    // ±1σ expected-move band (shaded) — where price most likely sits at expiry.
    if (sigmaBand) {
      shapes.push({
        type: "rect", xref: "paper", x0: 0, x1: 1, yref: "y",
        y0: sigmaBand[0], y1: sigmaBand[1],
        fillcolor: "rgba(0,255,204,0.06)", line: { width: 0 }, layer: "below",
      });
    }

    // Spot (cyan solid) and γ-flip (gold dashed) horizontal reference lines.
    shapes.push({
      type: "line", xref: "paper", x0: 0, x1: 1, yref: "y",
      y0: spot, y1: spot, line: { color: C.cyan, width: 1.5 },
    });
    annotations.push({
      xref: "paper", x: 0.995, yref: "y", y: spot, xanchor: "right",
      yanchor: "bottom", text: `spot ${spot.toFixed(1)}`, showarrow: false,
      font: { color: C.cyan, size: 9 }, bgcolor: "rgba(5,10,20,0.7)",
    });
    if (flip != null) {
      shapes.push({
        type: "line", xref: "paper", x0: 0, x1: 1, yref: "y",
        y0: flip, y1: flip, line: { color: C.gold, width: 1, dash: "dash" },
      });
      annotations.push({
        xref: "paper", x: 0.005, yref: "y", y: flip, xanchor: "left",
        yanchor: "top", text: `γ-flip ${flip.toFixed(1)}`, showarrow: false,
        font: { color: C.gold, size: 9 }, bgcolor: "rgba(5,10,20,0.7)",
      });
    }

    // Call/put-wall callouts at the tip of each wall's bar.
    const wall = (strike: number | null, txt: string, col: string) => {
      if (strike == null) return;
      const bar = bars.find((b) => b.strike === strike);
      if (!bar) return;
      annotations.push({
        xref: "x", x: bar.gex / 1e6, yref: "y", y: strike,
        xanchor: bar.gex >= 0 ? "left" : "right", yanchor: "middle",
        text: ` ${txt} `, showarrow: false,
        font: { color: col, size: 9, family: "Courier New, monospace" },
      });
    };
    wall(model.callWall, "call wall", C.pos);
    wall(model.putWall, "put wall", C.neg);

    const layout = baseLayout({
      height: HEIGHT,
      uirevision: "gamma-profile",
      bargap: 0.15,
      margin: { l: 56, r: 16, t: 10, b: 34 },
      xaxis: {
        gridcolor: C.grid, color: C.text, zerolinecolor: C.body, zerolinewidth: 1.5,
        title: { text: "← dealer short γ   ·   GEX $M   ·   dealer long γ →",
                 font: { size: 9, color: C.label } },
      },
      yaxis: {
        gridcolor: C.grid, color: C.text, range: [yLo, yHi],
        title: { text: "strike", font: { size: 9 } }, tickformat: ".0f",
      },
      shapes, annotations, showlegend: false,
    });
    return { data, layout, maxAbsGex };
  }, [model]);

  if (!model || !fig) {
    const closed = !marketIsOpen();
    return (
      <div className="flex h-[180px] flex-col items-center justify-center gap-2 border border-grid bg-[#0A1628] px-4 text-center">
        <div className="flex items-center gap-2 text-[11px] tracking-[0.08em] text-label">
          GAMMA PROFILE
          {closed && (
            <span className="border border-grid px-1.5 py-0.5 text-[9px] text-gold">
              MARKET CLOSED
            </span>
          )}
        </div>
        <div className="max-w-[60ch] text-xs leading-relaxed text-label">
          {closed
            ? "No gamma exposure to show — the U.S. options market is closed. GEX is built from live open interest and dealer gamma by strike, which only populate while the market is open. This panel fills automatically at the next open (9:30 ET)."
            : "No gamma data for this ticker — open interest is too sparse right now to build a profile."}
        </div>
      </div>
    );
  }

  const netB = model.netGex / 1e9;
  const regime = model.netGex >= 0
    ? "positive — vol-suppressing (dealers buy dips / sell rips)"
    : "negative — vol-amplifying (dealers chase the move)";

  return (
    <div className="border border-grid bg-[#0A1628] p-2">
      <div className="mb-2 flex flex-wrap items-center gap-2">
        <div className="text-[11px] tracking-[0.08em] text-label">GAMMA PROFILE</div>
        {chip("NET GEX", `$${netB.toFixed(2)}B`, model.netGex >= 0 ? C.pos : C.neg)}
        {chip("γ-FLIP", model.flip != null ? `$${model.flip.toFixed(1)}` : "—", C.gold)}
        {chip("CALL WALL", model.callWall != null ? `$${model.callWall}` : "—", C.pos)}
        {chip("PUT WALL", model.putWall != null ? `$${model.putWall}` : "—", C.neg)}
        <div className="ml-auto max-w-[42ch] text-right text-[9px] leading-tight text-label">
          {regime}
        </div>
      </div>
      <Plot data={fig.data as never} layout={fig.layout as never}
        config={{ displayModeBar: false }} style={{ width: "100%" }} useResizeHandler />
    </div>
  );
}
