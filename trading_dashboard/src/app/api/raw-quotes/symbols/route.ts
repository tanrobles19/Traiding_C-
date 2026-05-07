import { NextResponse } from "next/server";
import { query } from "@/lib/db";

// GET /api/raw-quotes/symbols
// Distinct symbols present in RawQuotes, with row counts and the
// latest id. Used by the spread chart page's symbol selector.

export async function GET() {
  try {
    const rows = await query<{ symbol: string; n: number | string; latest_id: number | string }>(
      `SELECT symbol, COUNT(*) AS n, MAX(id) AS latest_id
       FROM RawQuotes
       WHERE symbol IS NOT NULL AND symbol <> ''
       GROUP BY symbol
       ORDER BY latest_id DESC`,
    );

    return NextResponse.json({
      symbols: rows.map((r) => ({
        symbol:    r.symbol,
        count:     Number(r.n),
        latest_id: Number(r.latest_id),
      })),
    });
  } catch (err) {
    const message = err instanceof Error ? err.message : "Unknown error";
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
