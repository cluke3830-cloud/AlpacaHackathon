"use client";
import { fmtPct, fmtNum, fmtUsd, type Stats } from "@/lib/stats";

function Row({ label, value, tone }: { label: string; value: string; tone?: "pos" | "neg" }) {
  return (
    <div className="flex items-baseline justify-between border-b border-grid/60 py-[5px]">
      <span className="text-[10px] tracking-[0.08em] text-label">{label}</span>
      <span className={`text-xs tabular-nums ${
        tone === "pos" ? "text-pos" : tone === "neg" ? "text-neg" : "text-body"}`}>
        {value}
      </span>
    </div>
  );
}

const tone = (v: number | null | undefined) =>
  v == null ? undefined : v > 0 ? ("pos" as const) : v < 0 ? ("neg" as const) : undefined;

export default function StatsPanel({
  stats, equity, dayPl, positionLabel,
}: {
  stats: Stats;
  equity: number | null;
  dayPl: number | null;
  positionLabel: string;
}) {
  return (
    <div className="border border-grid bg-panel/40 px-3 py-2">
      <div className="mb-1 text-[11px] tracking-[0.14em] text-cyan">STATS</div>
      <Row label="EQUITY" value={fmtUsd(equity)} />
      <Row label="TODAY P&L" value={fmtUsd(dayPl)} tone={tone(dayPl)} />
      <Row label="RETURN" value={fmtPct(stats.totalReturn)} tone={tone(stats.totalReturn)} />
      <Row label="CAGR" value={fmtPct(stats.cagr)} tone={tone(stats.cagr)} />
      <Row label="MAX DD" value={fmtPct(stats.maxDD)} tone={stats.maxDD < 0 ? "neg" : undefined} />
      <Row label="SHARPE" value={fmtNum(stats.sharpe)} tone={tone(stats.sharpe)} />
      <Row label="SORTINO" value={fmtNum(stats.sortino)} tone={tone(stats.sortino)} />
      <Row label="CALMAR" value={fmtNum(stats.calmar)} />
      <Row label="VAR 95%" value={fmtPct(stats.var95)} tone={stats.var95 != null ? "neg" : undefined} />
      <Row label="VOL (ANN)" value={fmtPct(stats.vol)} />
      <Row label="WIN RATE" value={fmtPct(stats.winRate, 1)} />
      <Row label="CURRENT POSITION" value={positionLabel} />
      <div className="pt-2 text-[9px] leading-snug text-label">
        {stats.nDays < 20
          ? `${stats.nDays} obs — Sharpe/Sortino/VaR are not meaningful yet and are shown for wiring, not inference.`
          : `${stats.nDays} observations · 252d annualization · historical VaR`}
      </div>
    </div>
  );
}
