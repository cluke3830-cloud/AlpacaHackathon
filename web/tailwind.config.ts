import type { Config } from "tailwindcss";

// Design tokens carried over verbatim from OptionDashboard so the two
// terminals read as one system (TC: "same as Option Dashboard's market section").
const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        bg: "#050A14",
        grid: "#0D1F33",
        text: "#8BA8C4",
        body: "#C8D8E8",
        gold: "#FFD700",
        pos: "#00FF99",
        neg: "#FF4444",
        cyan: "#00FFCC",
        headerline: "#0D2137",
        label: "#4A7A9B",
        magenta: "#FF00FF",
        panel: "#0A1220",
      },
      fontFamily: { mono: ["Courier New", "monospace"] },
    },
  },
  plugins: [],
};
export default config;
