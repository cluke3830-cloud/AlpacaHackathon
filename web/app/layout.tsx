import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Alpaca AI Hackathon — Options Terminal",
  description:
    "Two-sleeve options agent: live portfolio, market regime, and the audited backtest.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="bg-bg text-body font-mono min-h-screen">{children}</body>
    </html>
  );
}
