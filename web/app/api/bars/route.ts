import { NextResponse } from "next/server";
import { bars } from "@/lib/alpaca";

export const dynamic = "force-dynamic";

export async function GET(req: Request) {
  const p = new URL(req.url).searchParams;
  const symbol = p.get("symbol") ?? "SPY";
  const timeframe = p.get("timeframe") ?? "1Day";
  const limit = Number(p.get("limit") ?? 1000);
  const start = p.get("start") ?? undefined;
  try {
    return NextResponse.json({ symbol, timeframe, bars: await bars(symbol, timeframe, start, limit) });
  } catch (e: any) {
    return NextResponse.json({ error: String(e?.message ?? e) }, { status: 502 });
  }
}
