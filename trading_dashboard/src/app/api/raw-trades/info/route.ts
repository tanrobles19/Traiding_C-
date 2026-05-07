import { NextResponse } from "next/server";
import { count, query } from "@/lib/db";

// GET /api/raw-trades/info
//
// Snapshot used by the /raw-trades page's status panel: total row
// count, unique-symbol count, and a per-symbol breakdown of the most
// recent symbols downloaded (for the user to recognise prior runs).

export async function GET() {
  try {
    const total = await count(`SELECT COUNT(*) AS n FROM RawTrades`);

    const perSymbol = await query<{ symbol: string; n: number; latest_id: number }>(
      `SELECT symbol, COUNT(*) AS n, MAX(id) AS latest_id
       FROM RawTrades
       GROUP BY symbol
       ORDER BY latest_id DESC
       LIMIT 8`,
    );

    return NextResponse.json({
      total,
      unique_symbols: perSymbol.length,
      recent: perSymbol.map((r) => ({
        symbol: r.symbol,
        rows:   Number(r.n),
      })),
      generated_at: Date.now(),
    });
  } catch (err) {
    const message = err instanceof Error ? err.message : "Unknown error";
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
