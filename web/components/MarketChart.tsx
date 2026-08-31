"use client";
import { useMemo } from "react";
import Plot from "./Plot";
import { C, baseLayout } from "@/lib/theme";
import { isoDay, monthlyTicks } from "@/lib/dateAxis";
import { buildRiskOnsets, type RiskOnset } from "@/lib/riskOnsets";
import { toHeikinAshi, type Bar } from "@/lib/heikinashi";

export default function MarketChart({ bars, vixByDay, highVix = 25, riskDays, fireDays, strongDays, buyDays, sellDays, msarBuyDays, msarSellDays, loading }: {
  bars: Bar[];
  vixByDay?: Record<string, number>;   // isoDay -> VIX close, for high-VIX shading
  highVix?: number;                    // stress shading threshold (default 25)
  riskDays?: string[];                 // amber-band days: regime tier (short-γ & VIX>=20)
  fireDays?: string[];                 // dot-gate days: firing tier (short-γ & VIX>=22)
  strongDays?: string[];               // full stack: + VIX9D>VIX + spot below gamma flip
  buyDays?: string[];                  // SMA timing RE-ENTER days (▲ green, below bar)
  sellDays?: string[];                 // SMA timing DE-RISK days (▼ red, below bar)
  msarBuyDays?: string[];              // MSAR timing RE-ENTER days (▲ cyan, below bar)
  msarSellDays?: string[];             // MSAR timing DE-RISK days (▼ orange, below bar)
  loading?: boolean;
}) {
  const fig = useMemo(() => {
    if (!bars.length) return null;
    const ha = toHeikinAshi(bars);
    // Gapless categorical x (one slot per trading day) — matches VixTermChart so
    // Row 1 and Row 2 stay aligned, and avoids the weekend-rangebreak clipping.
    const x = ha.map((b) => isoDay(b.t));
    const traces: object[] = [{
      type: "candlestick", name: "SPY",
      x, open: ha.map((b) => b.o), high: ha.map((b) => b.h),
      low: ha.map((b) => b.l), close: ha.map((b) => b.c),
      increasing: { line: { color: C.pos, width: 1 }, fillcolor: C.pos },
      decreasing: { line: { color: C.neg, width: 1 }, fillcolor: C.neg },
      showlegend: false,
    }];

    // High-VIX (overt stress) red bands — contiguous runs of days with VIX >= threshold.
    const shapes: object[] = [];
    if (vixByDay) {
      const hot = x.map((d) => (vixByDay[d] ?? 0) >= highVix);
      let i = 0;
      while (i < hot.length) {
        if (hot[i]) {
          let j = i;
          while (j < hot.length && hot[j]) j++;
          shapes.push({ type: "rect", xref: "x", yref: "paper",
            x0: i - 0.5, x1: j - 1 + 0.5, y0: 0, y1: 1,
            fillcolor: "rgba(255,68,68,0.10)", line: { width: 0 }, layer: "below" });
          i = j;
        } else i++;
      }
    }

    // ELEVATED-RISK amber bands: contiguous runs of short-γ + VIX>=20 days
    // (historical backtest + live log). Drawn UNDER the red VIX>=25 stress bands,
    // so red = acute stress, amber = the gamma-sharpened elevated-risk regime.
    // ~2x elevated drop risk — a risk regime, NOT a forecast (still ~83% no-drop).
    const annotations: object[] = [];
    if (riskDays && riskDays.length) {
      const flagged = new Set(riskDays);
      const on = x.map((d) => flagged.has(d));
      let i = 0;
      while (i < on.length) {
        if (on[i]) {
          let j = i;
          while (j < on.length && on[j]) j++;
          shapes.push({ type: "rect", xref: "x", yref: "paper",
            x0: i - 0.5, x1: j - 1 + 0.5, y0: 0, y1: 1,
            fillcolor: "rgba(255,176,0,0.09)", line: { width: 0 }, layer: "below" });
          i = j;
        } else i++;
      }

    }

    // Signal-onset dots: the FIRING tier (short-γ & VIX>=22, tighter than the
    // amber regime bands), scored over a 20-trading-day window (~1 month; the
    // 10d window clipped slow-grind declines). EVERY onset shown, no hindsight:
    //   gold ◆ = hit (>=5% drop, ~31% historically) · grey ✕ = miss (~69%) ·
    //   cyan ◇ = pending (window still open — resolves live as bars arrive).
    if (fireDays && fireDays.length) {
      const onsets = buildRiskOnsets(bars, new Set(fireDays),
                                     new Set(strongDays ?? []));
      // Two-intensity: STRONG onsets (full mechanism stack — front inverted +
      // below flip; 37.5% hit) render bigger with a red outline; normal onsets
      // (~31% hit) stay subtle. Misses always visible — the honest ~2/3.
      // CRISIS-FIRST styling (TC): the ★ crisis catches are the headline —
      // dip hits stay visible but secondary; misses stay honest.
      const style: Record<RiskOnset["outcome"],
        { color: string; symbol: string; size: number; label: string }> = {
        crisis:  { color: C.neg, symbol: "star", size: 14,
                   label: "fired — CRISIS: ≥10% drop followed within 20d" },
        hit:     { color: C.gold, symbol: "diamond", size: 8,
                   label: "fired — a 5-10% dip followed within 20d" },
        miss:    { color: "rgba(139,168,196,0.85)", symbol: "x", size: 7,
                   label: "fired — no ≥5% drop followed (false alarm)" },
        pending: { color: C.cyan, symbol: "diamond-open", size: 9,
                   label: "fired — outcome window still open (live)" },
      };
      for (const kind of ["miss", "hit", "crisis", "pending"] as const) {
        for (const strong of [false, true]) {
          const pts = onsets.filter((o) => o.outcome === kind && o.strong === strong);
          if (!pts.length) continue;
          const s = style[kind];
          traces.push({
            type: "scatter", mode: "markers",
            x: pts.map((o) => x[o.idx]), y: pts.map((o) => ha[o.idx].h),
            marker: { symbol: s.symbol, size: strong ? s.size + 4 : s.size,
                      color: s.color,
                      line: kind === "crisis" ? { width: 1.5, color: C.gold }
                        : strong ? { width: 2, color: C.neg }
                        : kind === "miss" ? { width: 1, color: s.color }
                                          : { width: 1, color: "#000" } },
            hovertext: pts.map((o) =>
              `${o.day}: ${strong ? "STRONG (front inverted + below flip) " : ""}${s.label}`),
            hoverinfo: "text", showlegend: false,
          });
        }
      }
      // annotate the most recent pending onset so the live firing is unmissable
      const pend = onsets.filter((o) => o.outcome === "pending");
      if (pend.length) {
        const p = pend[pend.length - 1];
        annotations.push({ x: x[p.idx], y: ha[p.idx].h,
          text: p.strong ? "⚠ STRONG fire" : "⚠ fired",
          showarrow: false, font: { color: p.strong ? C.neg : C.cyan, size: 9 },
          yanchor: "bottom", yshift: 8 });
      }
    }

    // VIX-timing entry/exit markers, drawn BELOW the bar low so they never
    // collide with the risk dots (above). Two independent signals can render
    // side by side (yShift separates them when both are on):
    //   SMA (green ▲ / red ▼): VIX vs 1.5x/1.0x of its 252d rolling mean —
    //     simple, validated 2007-2026 (Sharpe 0.70 vs 0.42 B&H).
    //   MSAR (cyan ▲ / orange ▼): 2-regime Markov-switching AR filter on
    //     log VIX — detects vol-of-vol regime shifts, faster in/out
    //     (Sharpe 1.01 vs SMA 0.90 on 2016-2026, maxDD -18% vs -27%).
    // Honest: drawdown-defense overlays, not buy/sell oracles — see caption.
    const addTimingMarkers = (
      buys: string[] | undefined, sells: string[] | undefined,
      buyColor: string, sellColor: string, label: string, yShift: number,
    ) => {
      if (!(buys && buys.length) && !(sells && sells.length)) return;
      const buySet = new Set(buys ?? []);
      const sellSet = new Set(sells ?? []);
      const sellX: string[] = [], sellY: number[] = [], sellT: string[] = [];
      const buyX: string[] = [], buyY: number[] = [], buyT: string[] = [];
      for (let i = 0; i < x.length; i++) {
        if (sellSet.has(x[i])) {
          sellX.push(x[i]); sellY.push(ha[i].l * yShift);
          sellT.push(`${x[i]}: ${label} SELL — de-risk to flat`);
        }
        if (buySet.has(x[i])) {
          buyX.push(x[i]); buyY.push(ha[i].l * yShift);
          buyT.push(`${x[i]}: ${label} BUY — re-enter long`);
        }
      }
      if (sellX.length) traces.push({
        type: "scatter", mode: "markers", name: `${label} de-risk`,
        x: sellX, y: sellY,
        marker: { symbol: "triangle-down", size: 11, color: sellColor,
                  line: { width: 1, color: "#000" } },
        hovertext: sellT, hoverinfo: "text", showlegend: false,
      });
      if (buyX.length) traces.push({
        type: "scatter", mode: "markers", name: `${label} re-enter`,
        x: buyX, y: buyY,
        marker: { symbol: "triangle-up", size: 11, color: buyColor,
                  line: { width: 1, color: "#000" } },
        hovertext: buyT, hoverinfo: "text", showlegend: false,
      });
    };
    addTimingMarkers(buyDays, sellDays, C.pos, C.neg, "SMA", 1.0);
    addTimingMarkers(msarBuyDays, msarSellDays, C.cyan, "#FF9500", "MSAR", 0.985);

    const ticks = monthlyTicks(bars.map((b) => b.t));
    const layout = baseLayout({
      height: 360,
      uirevision: "spy-daily",
      xaxis: { type: "category", gridcolor: C.grid, color: C.text,
               rangeslider: { visible: false },
               tickmode: "array", tickvals: ticks.tickvals, ticktext: ticks.ticktext },
      yaxis: { gridcolor: C.grid, color: C.text, side: "left",
               title: { text: "SPY", font: { size: 9 } } },
      shapes, annotations,
    });
    return { data: traces, layout };
  }, [bars, vixByDay, highVix, riskDays, fireDays, strongDays,
      buyDays, sellDays, msarBuyDays, msarSellDays]);

  if (!fig) {
    return (
      <div className="flex h-[360px] items-center justify-center text-xs text-label">
        {loading ? "loading market data…" : "no SPY data"}
      </div>
    );
  }
  return (
    <div className={loading ? "opacity-40 transition-opacity" : "transition-opacity"}>
      <Plot data={fig.data as never} layout={fig.layout as never}
        config={{ displayModeBar: false, doubleClick: "autosize", scrollZoom: false }}
        style={{ width: "100%" }} useResizeHandler />
    </div>
  );
}
