import { NextResponse } from "next/server";
import { query, count } from "@/lib/db";

// GET /api/utils/info
//
// Snapshot of the data-pipeline state used by the /utils page's
// "Configuration & Results" panel:
//   - symbol_count, symbol_range (first 5 + last 5)
//   - row counts for HistoryByMin, RelativeVolumeRatioHour,
//     minute_candlesticks, trades
//
// Trading-config CONSTANTS (Float Threshold, Price Range, etc.) live
// on the page itself — they're truly constant so we don't bother
// round-tripping to MySQL for them.

export async function GET() {
  try {
    const symbols = await query<{ symbol: string | null }>(
      `SELECT DISTINCT symbol FROM RelativeVolumeRatioHour
       WHERE symbol IS NOT NULL
       ORDER BY symbol ASC`
    );
    const list = symbols.map((r) => r.symbol).filter(Boolean) as string[];

    const range =
      list.length === 0
        ? ""
        : list.length <= 10
        ? list.join(", ")
        : `${list.slice(0, 5).join(", ")} … ${list.slice(-5).join(", ")}`;

    const [historyByMin, rvHour, minuteCandlesticks, trades] = await Promise.all([
      count(`SELECT COUNT(*) AS n FROM HistoryByMin`),
      count(`SELECT COUNT(*) AS n FROM RelativeVolumeRatioHour`),
      count(`SELECT COUNT(*) AS n FROM minute_candlesticks`).catch(() => 0),
      count(`SELECT COUNT(*) AS n FROM trades`).catch(() => 0),
    ]);

    return NextResponse.json({
      symbol_count:    list.length,
      symbol_range:    range,
      counts: {
        HistoryByMin:            historyByMin,
        RelativeVolumeRatioHour: rvHour,
        minute_candlesticks:     minuteCandlesticks,
        trades:                  trades,
      },
      generated_at: Date.now(),
    });
  } catch (err) {
    const message = err instanceof Error ? err.message : "Unknown error";
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
