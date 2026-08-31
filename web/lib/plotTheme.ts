/**
 * Plotly theme.
 *
 * ⚠ EVERY EXPORT HERE IS A FACTORY, NOT A SHARED CONSTANT, AND THAT IS LOAD-BEARING.
 *
 * Plotly MUTATES the layout object it is handed — it writes computed state
 * (`type`, `range`, `_length`, autorange results…) directly onto the axis
 * objects. An earlier version of this file exported a single `AXIS` const that
 * both `LAYOUT.xaxis` and `LAYOUT.yaxis` pointed at, spread into every chart.
 * The result: the historical-equity chart, whose x really is date strings, set
 * `type: "date"` on that shared object, and the Monte Carlo chart then rendered
 * its 0..1260 day counts as epoch milliseconds — "Jan 1256", "Dec 1969", NaN
 * hovers, a nonsense 1000–2000 axis. The stats were right; only the drawing was
 * poisoned, which is the worst kind of bug because it looks like a styling
 * problem.
 *
 * So: call the functions, never reuse a returned object across two charts, and
 * set an explicit axis `type` wherever the data could be mistaken for dates.
 */
import { C as BASE } from "./theme";

export const C = {
  ...BASE,
  ours: "#FF4444",     // sketch: red = our book
  spy: "#3B9EFF",      // sketch: blue = benchmark
  magenta: "#FF00FF",
};

/** A fresh axis config. Never share the returned object between charts. */
export function axis(overrides: Record<string, unknown> = {}) {
  return {
    gridcolor: "#0D1F33",
    zerolinecolor: "#0D2137",
    linecolor: "#0D2137",
    tickfont: { color: "#4A7A9B", size: 10, family: "Courier New, monospace" },
    ...overrides,
  };
}

/** A fresh base layout. Axes are rebuilt per call, never aliased. */
export function layout(overrides: Record<string, unknown> = {}) {
  const { xaxis, yaxis, ...rest } = overrides as any;
  return {
    paper_bgcolor: "rgba(0,0,0,0)",
    plot_bgcolor: "rgba(0,0,0,0)",
    font: { family: "Courier New, monospace", color: "#8BA8C4", size: 11 },
    margin: { l: 52, r: 16, t: 28, b: 36 },
    hovermode: "x unified" as const,
    legend: {
      orientation: "h" as const,
      y: 1.12,
      x: 0,
      font: { size: 10, color: "#8BA8C4" },
      bgcolor: "rgba(0,0,0,0)",
    },
    ...rest,
    xaxis: axis(xaxis ?? {}),
    yaxis: axis(yaxis ?? {}),
  };
}

/** Axis title helper — Plotly wants a nested object, and it reads badly inline. */
export const axisTitle = (text: string) => ({
  text,
  font: { size: 9, color: C.label },
});

export const CONFIG = { displayModeBar: false, responsive: true };
