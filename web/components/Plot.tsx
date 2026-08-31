"use client";
import dynamic from "next/dynamic";

// Plotly touches `window` at import time, so it can never be server-rendered.
const Plot = dynamic(() => import("react-plotly.js"), {
  ssr: false,
  loading: () => <div className="h-full w-full animate-pulse bg-panel" />,
});
export default Plot;
