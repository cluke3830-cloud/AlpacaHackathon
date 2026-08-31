// Aesthetic source of truth: Past Strategies (Failed Ones)/Alpaca/
// Option_Session/Session_3.py + Session_5.py. Do not improvise colors.
export const C = {
  bg: "#050A14",
  grid: "#0D1F33",
  grid3d: "#1A2A3A",
  text: "#8BA8C4",
  body: "#C8D8E8",
  gold: "#FFD700",
  pos: "#00FF99",
  neg: "#FF4444",
  cyan: "#00FFCC",
  red2: "#FF6B6B",
  zero: "#1A3A55",
  label: "#4A7A9B",
  dim: "#555555",
  magenta: "#FF00FF",   // MC median / our option-timing put markers
  palette: ["#FF2D55", "#FF6B35", "#FFD700", "#00FF99", "#00CCFF",
            "#7B68EE", "#BB86FC", "#FF69B4", "#4ECDC4", "#96CEB4"],
} as const;

export const FONT = { family: "Courier New, monospace", color: C.text, size: 11 };

// Blue IV-surface colorscale (navy → blue → cyan) — replaces Plasma's
// purple/red so the 3D surfaces match the dashboard's cyan identity.
export const SURFACE_SCALE: [number, string][] = [
  [0.0, "#0D1F33"],
  [0.25, "#15457F"],
  [0.5, "#1E78C8"],
  [0.75, "#22B8E8"],
  [1.0, "#7CF5E6"],
];

// Base Plotly layout every chart starts from (Session_3.py:362-364 pattern).
export function baseLayout(overrides: Record<string, unknown> = {}) {
  return {
    template: "plotly_dark",
    paper_bgcolor: C.bg,
    plot_bgcolor: C.bg,
    font: FONT,
    margin: { l: 50, r: 60, t: 36, b: 36 },
    xaxis: { gridcolor: C.grid, color: C.text },
    yaxis: { gridcolor: C.grid, color: C.text },
    ...overrides,
  };
}
