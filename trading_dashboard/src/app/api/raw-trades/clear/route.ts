import { NextResponse } from "next/server";
import { execute } from "@/lib/db";

// POST /api/raw-trades/clear — TRUNCATE both RawTrades AND RawQuotes.
//
// 2026-05-05: extended to clear both tables now that the downloader
// populates them together. The endpoint name stays
// `/api/raw-trades/clear` for backwards compatibility with the
// dashboard's existing trigger.
export async function POST() {
  try {
    await execute(`TRUNCATE TABLE RawTrades`);
    await execute(`TRUNCATE TABLE RawQuotes`);
    return NextResponse.json({ ok: true });
  } catch (err) {
    const message = err instanceof Error ? err.message : "Unknown error";
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
