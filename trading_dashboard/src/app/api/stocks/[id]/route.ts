import { NextRequest, NextResponse } from "next/server";
import { execute } from "@/lib/db";

// ── DELETE /api/stocks/:id ───────────────────────────────────────
// Removes a single row from the Stocks master registry.
// Returns the number of affected rows (0 = id not found, 1 = deleted).

export async function DELETE(
  _req: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  const { id } = await params;
  const numericId = Number(id);

  if (!Number.isInteger(numericId) || numericId <= 0) {
    return NextResponse.json({ error: "Invalid id" }, { status: 400 });
  }

  try {
    const { affectedRows } = await execute(
      `DELETE FROM Stocks WHERE id = ?`,
      [numericId]
    );
    return NextResponse.json({ ok: true, affectedRows });
  } catch (err) {
    const message = err instanceof Error ? err.message : "Unknown error";
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
