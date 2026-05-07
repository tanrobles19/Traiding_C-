import { NextResponse } from "next/server";
import { execute } from "@/lib/db";

// ── POST /api/signals/clear ──────────────────────────────────────
// Truncates TradeSignalsBuyPerSecond. TRUNCATE is faster than DELETE on
// large tables and resets auto-increment counters. Use with care — this
// wipes ALL rows.

export async function POST() {
  try {
    await execute(`TRUNCATE TABLE TradeSignalsBuyPerSecond`);
    return NextResponse.json({ ok: true });
  } catch (err) {
    const message = err instanceof Error ? err.message : "Unknown error";
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
