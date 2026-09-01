"use client";
import { useCallback, useEffect, useMemo, useState } from "react";
import TabNav from "@/components/TabNav";
import EquityVsSpy, { type ChartKind } from "@/components/EquityVsSpy";
import StatsPanel from "@/components/StatsPanel";
import AllocationPie from "@/components/AllocationPie";
import TradeLog from "@/components/TradeLog";
import VolSurface, { type SurfaceData } from "@/components/VolSurface";
import { computeStats } from "@/lib/stats";
import type { Account, Position, Order, PortfolioHistory } from "@/lib/alpaca";

// Alpaca's portfolio-history `period` values. 1D/1W render at 30-minute
// resolution (the API's finest legal grain, probed 2026-09-01); longer periods
// are daily because Alpaca rejects intraday grains beyond 1W. Default 1W: the
// densest window that shows the account's whole live life.
const PERIODS = ["1D", "1W", "1M", "3M", "6M", "1Y"] as const;
type Period = (typeof PERIODS)[number];
const KINDS: ChartKind[] = ["line", "area"];
const POLL_MS = 30_000;

function Pill({ on, onClick, children }: { on: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      onClick={onClick}
      className={`px-2 py-[2px] text-[10px] border transition-colors ${
        on ? "border-cyan text-cyan" : "border-grid text-label hover:border-label"
      }`}
    >
      {children}
    </button>
  );
}

export default function PortfolioPage() {
  const [period, setPeriod] = useState<Period>("1W");
  const [kind, setKind] = useState<ChartKind>("area");
  const [acct, setAcct] = useState<Account | null>(null);
  const [pos, setPos] = useState<Position[]>([]);
  const [hist, setHist] = useState<PortfolioHistory | null>(null);
  const [spy, setSpy] = useState<(number | null)[] | null>(null);
  const [timeframe, setTimeframe] = useState<string>("30Min");
  const [trades, setTrades] = useState<Order[]>([]);
  const [surface, setSurface] = useState<SurfaceData | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    try {
      const [p, t, m] = await Promise.all([
        fetch(`/api/portfolio?period=${period}`).then((r) => r.json()),
        fetch("/api/trades?limit=500").then((r) => r.json()),
        fetch("/api/market").then((r) => r.json()).catch(() => null),
      ]);
      if (p.error) throw new Error(p.error);
      setAcct(p.account);
      setPos(p.positions ?? []);
      setHist(p.history ?? null);
      setSpy(p.spy ?? null);
      setTimeframe(p.timeframe ?? "1D");
      setTrades(t.trades ?? []);
      if (m && !m.error) setSurface(m.surface ?? null);
      setErr(null);
    } catch (e: any) {
      setErr(String(e?.message ?? e));
    } finally {
      setLoading(false);
    }
  }, [period]);

  useEffect(() => {
    load();
    const id = setInterval(load, POLL_MS);
    return () => clearInterval(id);
  }, [load]);

  const intraday = timeframe !== "1D";
  const times = useMemo(
    () => (hist?.timestamp ?? []).map((s) => new Date(s * 1000).toISOString()),
    [hist]
  );
  const ours = hist?.equity ?? [];

  // Stats from DAILY closes even when the chart draws 30-min points: every
  // annualized figure in stats.ts assumes 252 periods/year, and feeding it
  // 13 bars a day would inflate vol/Sharpe by ~sqrt(13). Last stamp per NY
  // session = the daily equity curve.
  const stats = useMemo(() => {
    if (!hist?.equity?.length) return computeStats([]);
    if (!intraday) return computeStats(hist.equity.filter((v) => v > 0));
    const daily: number[] = [];
    let prevDay = "";
    hist.timestamp.forEach((ts, i) => {
      const d = new Date(ts * 1000).toLocaleDateString("en-CA", { timeZone: "America/New_York" });
      if (d !== prevDay) { daily.push(hist.equity[i]); prevDay = d; }
      else daily[daily.length - 1] = hist.equity[i];
    });
    return computeStats(daily.filter((v) => v > 0));
  }, [hist, intraday]);

  // Long / short / cash. A long PUT is short-delta exposure, so it is grouped
  // as SHORT here rather than by the broker's own "long the contract" wording --
  // the pie is about market exposure, which is what a reader wants from it.
  const alloc = useMemo(() => {
    let long = 0, short = 0;
    for (const p of pos) {
      const v = Math.abs(p.market_value);
      const isPut = p.asset_class === "us_option" && /P\d{8}$/.test(p.symbol);
      const shortSide = p.qty < 0 || p.side === "short";
      if (isPut !== shortSide) short += v; else long += v;
    }
    return { long, short, cash: Math.max(acct?.cash ?? 0, 0) };
  }, [pos, acct]);

  const positionLabel = pos.length
    ? `${pos.length} open · ${alloc.long > alloc.short ? "NET LONG" : "NET SHORT"}`
    : "FLAT";

  const dayPl = acct ? acct.equity - acct.last_equity : null;

  return (
    <main className="min-h-screen">
      <TabNav active="/" />

      {err && (
        <div className="mx-4 mt-3 border border-neg/60 bg-neg/10 px-3 py-2 text-xs text-neg">
          {err}
        </div>
      )}

      <div className="flex flex-wrap items-center gap-3 px-4 py-2">
        <div className="flex gap-1">
          {PERIODS.map((p) => (
            <Pill key={p} on={p === period} onClick={() => setPeriod(p)}>{p}</Pill>
          ))}
        </div>
        <div className="flex gap-1">
          {KINDS.map((k) => (
            <Pill key={k} on={k === kind} onClick={() => setKind(k)}>{k.toUpperCase()}</Pill>
          ))}
        </div>
        <span className="ml-auto text-[10px] text-label">
          {acct ? `ACCT ${acct.account_number} · ${acct.status}` : loading ? "connecting…" : "—"}
        </span>
      </div>

      <div className="grid gap-3 px-4 pb-4 lg:grid-cols-[1fr_280px]">
        <section className="border border-grid bg-panel/40 p-2">
          <div className="mb-1 flex items-baseline gap-3 px-1">
            <span className="text-[11px] tracking-[0.14em] text-cyan">PORTFOLIO vs SPY</span>
            <span className="text-[10px] text-ours">— OURS</span>
            <span className="text-[10px] text-spy">— SPY</span>
            <span className="ml-auto text-[10px] text-label">
              {intraday ? "30-MIN MARKS" : "DAILY"} · {ours.length} PTS · REBASED 100
            </span>
          </div>
          <EquityVsSpy times={times} ours={ours} spy={spy} intraday={intraday} kind={kind} />
        </section>

        <StatsPanel
          stats={stats}
          equity={acct?.equity ?? null}
          dayPl={dayPl}
          positionLabel={positionLabel}
        />
      </div>

      <div className="grid gap-3 px-4 pb-4 lg:grid-cols-[280px_1fr]">
        <section className="border border-grid bg-panel/40 p-2">
          <div className="mb-1 px-1 text-[11px] tracking-[0.14em] text-cyan">ALLOCATION</div>
          <AllocationPie long={alloc.long} short={alloc.short} cash={alloc.cash} />
        </section>

        <section className="border border-grid bg-panel/40 p-2">
          <div className="mb-1 px-1 text-[11px] tracking-[0.14em] text-cyan">
            S&amp;P 500 VOLATILITY SURFACE{" "}
            <span className="text-label">
              · {surface?.symbols?.length ?? 0} names × {surface?.dates?.length ?? 0} sessions
              · {surface?.window ?? 10}d realized, annualized
            </span>
          </div>
          <VolSurface data={surface} height={300} />
        </section>
      </div>

      <div className="px-4 pb-8">
        <TradeLog trades={trades} />
      </div>
    </main>
  );
}
