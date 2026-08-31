import { NextResponse } from "next/server";
import { account, positions, portfolioHistory } from "@/lib/alpaca";

export const dynamic = "force-dynamic";

/** Account + open positions + Alpaca's own equity curve, in one round trip. */
export async function GET(req: Request) {
  const period = new URL(req.url).searchParams.get("period") ?? "1M";
  // Intraday only makes sense on short windows; Alpaca rejects 1Min on 1Y.
  const timeframe = ["1D", "1W"].includes(period) ? "15Min" : "1D";
  try {
    const [acct, pos, hist] = await Promise.all([
      account(),
      positions(),
      portfolioHistory(period, timeframe),
    ]);
    return NextResponse.json({ account: acct, positions: pos, history: hist, period, timeframe });
  } catch (e: any) {
    return NextResponse.json({ error: String(e?.message ?? e) }, { status: 502 });
  }
}
