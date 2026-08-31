/** One Plotly theme for every chart, so the three tabs read as one terminal. */
export const AXIS = {
  gridcolor: "#0D1F33",
  zerolinecolor: "#0D2137",
  linecolor: "#0D2137",
  tickfont: { color: "#4A7A9B", size: 10, family: "Courier New, monospace" },
  titlefont: { color: "#4A7A9B", size: 10 },
};

export const LAYOUT = {
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
  xaxis: AXIS,
  yaxis: AXIS,
};

export const CONFIG = { displayModeBar: false, responsive: true };

// Canonical palette lives in lib/theme.ts (carried from OptionDashboard, whose
// own header says "Do not improvise colors"). Re-exported here with the two
// sketch-specific roles added, so there is ONE source of truth for hues.
import { C as BASE } from "./theme";

export const C = {
  ...BASE,
  ours: "#FF4444",     // sketch: red = our book
  spy: "#3B9EFF",      // sketch: blue = benchmark
  magenta: "#FF00FF",
};
