import { NextResponse } from "next/server";
import { promises as fs } from "fs";
import path from "path";

export const dynamic = "force-dynamic";

/**
 * Backtest results are PRECOMPUTED by the Python research side and exported to
 * public/backtest.json (export_backtest_json.py). They are deliberately not
 * recomputed here: the numbers on this tab must be the same ones that went
 * through the audit stack (walk-forward OOS, permutation null, Monte Carlo),
 * and a TypeScript reimplementation would be a second, unvalidated source of
 * truth for the most important figures in the submission.
 */
export async function GET() {
  try {
    const p = path.join(process.cwd(), "public", "backtest.json");
    return NextResponse.json(JSON.parse(await fs.readFile(p, "utf-8")));
  } catch {
    return NextResponse.json(
      { error: "backtest.json not found — run scripts/export_backtest_json.py" },
      { status: 404 }
    );
  }
}
