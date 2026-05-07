import { NextResponse } from "next/server";
import { execute } from "@/lib/db";

// ── POST /api/orders/clear ───────────────────────────────────────
// Truncates Orders. Wipes ALL rows.

export async function POST() {
  try {
    await execute(`TRUNCATE TABLE Orders`);
    return NextResponse.json({ ok: true });
  } catch (err) {
    const message = err instanceof Error ? err.message : "Unknown error";
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
