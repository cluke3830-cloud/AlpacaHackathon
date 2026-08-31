import { NextResponse } from "next/server";
import { orders } from "@/lib/alpaca";

export const dynamic = "force-dynamic";

/** Trade log. Filled orders first -- an unfilled order is not a trade. */
export async function GET(req: Request) {
  const limit = Number(new URL(req.url).searchParams.get("limit") ?? 200);
  try {
    const all = await orders(Math.min(limit, 500));
    const filled = all.filter((o) => o.filled_qty > 0);
    return NextResponse.json({ trades: filled, submitted: all.length, filled: filled.length });
  } catch (e: any) {
    return NextResponse.json({ error: String(e?.message ?? e) }, { status: 502 });
  }
}
