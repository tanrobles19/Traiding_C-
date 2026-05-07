import { NextResponse } from "next/server";
import { query } from "@/lib/db";

// Quick top-level stats for the header / overview tiles.
// Cheap COUNT(*)s — only fast if the tables are small. For the larger
// tables (trades, etc.) we'd swap to information_schema or cached counts.
export async function GET() {
  try {
    const stats = await query<{ table_name: string; n: number | string }>(
      `SELECT 'TradeSignalsBuyPerSecond' AS table_name, COUNT(*) AS n FROM TradeSignalsBuyPerSecond
       UNION ALL
       SELECT 'Orders', COUNT(*) FROM Orders
       UNION ALL
       SELECT 'Stocks', COUNT(*) FROM Stocks
       UNION ALL
       SELECT 'RelativeVolumeRatioHour', COUNT(*) FROM RelativeVolumeRatioHour`
    );

    const out: Record<string, number> = {};
    for (const r of stats) out[r.table_name] = Number(r.n);

    return NextResponse.json({
      counts: out,
      generated_at: Date.now(),
    });
  } catch (err) {
    const message = err instanceof Error ? err.message : "Unknown error";
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
