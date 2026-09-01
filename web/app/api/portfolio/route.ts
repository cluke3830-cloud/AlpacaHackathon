import { NextResponse } from "next/server";
import { account, positions, portfolioHistory, bars } from "@/lib/alpaca";
import type { PortfolioHistory } from "@/lib/alpaca";

export const dynamic = "force-dynamic";

/**
 * Account + open positions + Alpaca's own equity curve + an SPY benchmark
 * series ALIGNED BY TIMESTAMP, in one round trip.
 *
 * Alpaca portfolio-history facts, probed empirically 2026-09-01 rather than
 * assumed: valid intraday grains are 1Min/5Min/15Min/1H only (30Min itself is
 * rejected with a 422), and any period longer than 1W rejects intraday grains
 * outright. So the 30-minute resolution the chart wants is built by fetching
 * 15Min and keeping the :00/:30 stamps; periods beyond 1W fall back to daily.
 *
 * The SPY series is aligned HERE, per portfolio timestamp, because the first
 * version aligned client-side by point COUNT (slice the last N daily closes
 * under N intraday equity points) -- two different time axes drawn as one.
 */
const INTRADAY_PERIODS = new Set(["1D", "1W"]);

/** Keep the :00/:30 stamps (epochs are exact quarter-hour marks, so modulo is
 *  safe), plus the final point -- the live mid-bar equity reading. */
function thinTo30Min(h: PortfolioHistory): PortfolioHistory {
  const keep: number[] = [];
  h.timestamp.forEach((ts, i) => {
    if (ts % 1800 === 0 || i === h.timestamp.length - 1) keep.push(i);
  });
  return {
    ...h,
    timestamp: keep.map((i) => h.timestamp[i]),
    equity: keep.map((i) => h.equity[i]),
    profit_loss: keep.map((i) => h.profit_loss[i]),
    profit_loss_pct: keep.map((i) => h.profit_loss_pct[i]),
  };
}

const etDate = (epochSec: number) =>
  new Date(epochSec * 1000).toLocaleDateString("en-CA", { timeZone: "America/New_York" });

/**
 * SPY closes at (or last known before) each portfolio timestamp.
 * Intraday: 30Min bars; a bar stamped T covers [T, T+30m), so its close is the
 * price AT T+30m -- the "effective time" the alignment uses. The fetch starts
 * days earlier so the window's first 09:30 stamp still finds a prior close.
 * Daily: match by New York calendar date (portfolio daily stamps land at
 * 20:00 ET, daily bars at 04:00 UTC -- same ET date, hours apart).
 */
async function spyAligned(ts: number[], intraday: boolean): Promise<(number | null)[]> {
  if (!ts.length) return [];
  if (intraday) {
    const start = new Date((ts[0] - 4 * 86400) * 1000).toISOString();
    const b = await bars("SPY", "30Min", start, 3000);
    const eff = b
      .map((x) => ({ t: Date.parse(x.t) / 1000 + 1800, c: x.c }))
      .sort((a, z) => a.t - z.t);
    let j = 0;
    return ts.map((T) => {
      while (j + 1 < eff.length && eff[j + 1].t <= T) j++;
      return eff.length && eff[j].t <= T ? eff[j].c : null;
    });
  }
  const start = new Date((ts[0] - 8 * 86400) * 1000).toISOString().slice(0, 10);
  const b = await bars("SPY", "1Day", start, 1500);
  const byDate = b
    .map((x) => ({ d: x.t.slice(0, 10), c: x.c }))
    .sort((a, z) => (a.d < z.d ? -1 : 1));
  let j = 0;
  return ts.map((T) => {
    const d = etDate(T);
    while (j + 1 < byDate.length && byDate[j + 1].d <= d) j++;
    return byDate.length && byDate[j].d <= d ? byDate[j].c : null;
  });
}

export async function GET(req: Request) {
  const period = new URL(req.url).searchParams.get("period") ?? "1W";
  const intraday = INTRADAY_PERIODS.has(period);
  try {
    const [acct, pos, raw] = await Promise.all([
      account(),
      positions(),
      portfolioHistory(period, intraday ? "15Min" : "1D"),
    ]);
    const hist = intraday ? thinTo30Min(raw) : raw;
    const spy = await spyAligned(hist.timestamp, intraday);
    return NextResponse.json({
      account: acct,
      positions: pos,
      history: hist,
      spy,
      period,
      timeframe: intraday ? "30Min" : "1D",
    });
  } catch (e: any) {
    return NextResponse.json({ error: String(e?.message ?? e) }, { status: 502 });
  }
}
