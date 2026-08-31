import { NextResponse } from "next/server";
import { promises as fs } from "fs";
import path from "path";

export const dynamic = "force-dynamic";

/**
 * MARKET tab payload: VIX family (CBOE), SPY daily (Alpaca), and the S&P
 * volatility surface. Precomputed by scripts/export_market_json.py -- the VIX
 * complex is not available from Alpaca at all, and the surface is a
 * multi-symbol aggregation better done once in Python than 21 fetches deep in
 * the browser.
 */
export async function GET() {
  try {
    const p = path.join(process.cwd(), "public", "market.json");
    return NextResponse.json(JSON.parse(await fs.readFile(p, "utf-8")));
  } catch {
    return NextResponse.json(
      { error: "market.json not found — run scripts/export_market_json.py" },
      { status: 404 }
    );
  }
}
