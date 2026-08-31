"use client";
import Link from "next/link";

const TABS = [
  { href: "/", label: "PORTFOLIO" },
  { href: "/market", label: "MARKET" },
  { href: "/backtest", label: "BACKTESTED" },
] as const;

export type TabHref = (typeof TABS)[number]["href"];

export default function TabNav({ active }: { active: TabHref }) {
  return (
    <header className="border-b border-headerline bg-[#051020]">
      <div className="flex items-baseline gap-4 px-4 pt-3">
        <h1 className="text-lg tracking-[0.14em] text-cyan">ALPACA AI HACKATHON</h1>
        <span className="text-[10px] tracking-[0.1em] text-label">
          TWO-SLEEVE OPTIONS AGENT · SPY
        </span>
      </div>
      <nav className="flex gap-1 px-4 py-2">
        {TABS.map((t) => (
          <Link
            key={t.href}
            href={t.href}
            className={`px-3 py-1 text-xs tracking-[0.06em] border ${
              t.href === active
                ? "border-cyan text-cyan"
                : "border-transparent text-label hover:text-body"
            }`}
          >
            {t.label}
          </Link>
        ))}
      </nav>
    </header>
  );
}
