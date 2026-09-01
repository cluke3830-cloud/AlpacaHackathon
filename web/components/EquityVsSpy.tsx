"use client";
import { useMemo } from "react";
import Plot from "./Plot";
import { layout, axisTitle, CONFIG, C } from "@/lib/plotTheme";

export type ChartKind = "line" | "area";

/**
 * Ours (red) vs SPY (blue), both rebased to 100 at the same instant.
 *
 * REBASING IS NOT COSMETIC: the account is ~$100k and SPY is ~$640, so on raw
 * axes one line is a flat floor under the other. Rebasing to a common 100 makes
 * the two directly comparable in percentage terms -- and both series MUST use
 * the same base instant or the comparison starts with a fabricated gap.
 *
 * INTRADAY MODE draws on a CATEGORY axis, not a date axis, on purpose: with
 * 30-minute points, a date axis spends ~70% of its width on closed-market
 * hours (overnight + weekend flat-line), which is exactly the dead space that
 * made the old chart unreadable. Categories pack the session bars edge to
 * edge; day boundaries come back as labeled ticks + separator lines.
 */
export default function EquityVsSpy({
  times, ours, spy, equityUsd, intraday = false, kind = "line", height = 440,
}: {
  times: string[];               // ISO timestamps, same length as ours
  ours: number[];                // account equity ($)
  spy: (number | null)[] | null; // SPY price aligned per timestamp (or null)
  equityUsd?: number[];          // raw $ for hover (defaults to `ours`)
  intraday?: boolean;
  kind?: ChartKind;
  height?: number;
}) {
  const { traces, xTicks, seps, lastLabels } = useMemo(() => {
    // Drop leading points from before the account had equity, then rebase both
    // series at the first index where BOTH have a value.
    let i0 = 0;
    while (i0 < ours.length && !(ours[i0] > 0 && (!spy || spy[i0] != null))) i0++;
    const t = times.slice(i0);
    const o = ours.slice(i0);
    const s = spy ? spy.slice(i0) : null;
    const usd = (equityUsd ?? ours).slice(i0);
    if (!o.length) return { traces: [], xTicks: null, seps: [], lastLabels: [] };

    const oBase = o[0];
    const sBase = s?.find((v) => v != null) ?? null;
    const oR = o.map((v) => (v / oBase) * 100);
    const sR = s && sBase ? s.map((v) => (v == null ? null : (v / sBase) * 100)) : null;

    // Category labels: "MM/DD HH:MM" intraday (unique per point, and the
    // unified-hover header shows them verbatim), ISO date for daily mode.
    const fmt = (iso: string) => {
      const d = new Date(iso);
      const day = d.toLocaleDateString("en-US", {
        timeZone: "America/New_York", month: "2-digit", day: "2-digit",
      });
      if (!intraday) return day;
      const hm = d.toLocaleTimeString("en-US", {
        timeZone: "America/New_York", hour: "2-digit", minute: "2-digit", hour12: false,
      });
      return `${day} ${hm}`;
    };
    const dow = (iso: string) =>
      new Date(iso).toLocaleDateString("en-US", { timeZone: "America/New_York", weekday: "short" }).toUpperCase();

    const x = intraday ? t.map(fmt) : t;

    // One labeled tick per ET session + a faint separator at each day start.
    let xTicks: { tickvals: string[]; ticktext: string[] } | null = null;
    let seps: string[] = [];
    if (intraday) {
      const tickvals: string[] = [];
      const ticktext: string[] = [];
      let prev = "";
      t.forEach((iso, i) => {
        const d = fmt(iso).slice(0, 5);
        if (d !== prev) {
          tickvals.push(x[i]);
          ticktext.push(`${dow(iso)} ${d}`);
          if (prev) seps.push(x[i]);
          prev = d;
        }
      });
      xTicks = { tickvals, ticktext };
    }

    const traces: any[] = [];
    if (kind === "area") {
      // Invisible 100-baseline so the fill shades ABOVE/BELOW breakeven,
      // instead of flooding down to zero and flattening the whole curve.
      traces.push({
        x, y: x.map(() => 100), type: "scatter", mode: "lines",
        line: { width: 0 }, hoverinfo: "skip", showlegend: false,
      });
    }
    traces.push({
      x, y: oR, type: "scatter", mode: "lines", name: "OURS",
      line: { color: C.ours, width: 2.2, shape: "spline", smoothing: 0.35 },
      fill: kind === "area" ? "tonexty" : undefined,
      fillcolor: kind === "area" ? "rgba(255,68,68,0.09)" : undefined,
      customdata: usd,
      hovertemplate: "%{y:.2f}  ·  $%{customdata:,.0f}<extra>OURS</extra>",
    });
    if (sR) {
      traces.push({
        x, y: sR, type: "scatter", mode: "lines", name: "SPY",
        line: { color: C.spy, width: 1.4 },
        connectgaps: true,
        hovertemplate: "%{y:.2f}<extra>SPY</extra>",
      });
    }

    const lastLabels = [
      { v: oR[oR.length - 1], color: C.ours },
      ...(sR ? [{ v: [...sR].reverse().find((v) => v != null) as number, color: C.spy }] : []),
    ];
    return { traces, xTicks, seps, lastLabels };
  }, [times, ours, spy, equityUsd, intraday, kind]);

  if (!traces.length) {
    return (
      <div className="flex h-[440px] items-center justify-center border border-grid text-xs text-label">
        no equity history yet — the account has not traded
      </div>
    );
  }

  const shapes: any[] = [
    { // breakeven line
      type: "line", xref: "paper", x0: 0, x1: 1, yref: "y", y0: 100, y1: 100,
      line: { color: "#2A4A66", width: 1, dash: "dot" },
    },
    ...seps.map((xv) => ({
      type: "line", xref: "x", x0: xv, x1: xv, yref: "paper", y0: 0, y1: 1,
      line: { color: "#0D1F33", width: 1 },
    })),
  ];

  const annotations = lastLabels.map((l, i) => ({
    xref: "paper", x: 1, yref: "y", y: l.v, xanchor: "left",
    text: ` ${l.v.toFixed(2)}`, showarrow: false,
    font: { size: 10, color: l.color, family: "Courier New, monospace" },
    bgcolor: "rgba(3,10,18,0.7)",
  }));

  return (
    <Plot
      data={traces}
      layout={layout({
        height,
        margin: { l: 52, r: 54, t: 16, b: 40 },
        showlegend: false,
        shapes,
        annotations,
        xaxis: intraday
          ? { type: "category", tickvals: xTicks?.tickvals, ticktext: xTicks?.ticktext, tickangle: 0 }
          : { type: "date" },
        yaxis: { type: "linear", title: axisTitle("INDEXED = 100") },
      })}
      config={CONFIG}
      style={{ width: "100%" }}
    />
  );
}
