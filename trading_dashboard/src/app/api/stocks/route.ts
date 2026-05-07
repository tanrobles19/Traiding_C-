import { NextRequest, NextResponse } from "next/server";
import { paginatedTableHandler } from "@/lib/handlers";
import { execute } from "@/lib/db";
import {
  STOCKS_COLUMNS,
  STOCKS_COLUMN_WHITELIST,
  STOCKS_DEFAULT_SORT,
  STOCKS_TABLE,
} from "@/lib/tables";

export async function GET(req: NextRequest) {
  return paginatedTableHandler(req, {
    table: STOCKS_TABLE,
    columnList: STOCKS_COLUMNS.map((c) => c.key),
    columnWhitelist: STOCKS_COLUMN_WHITELIST,
    defaultSort: STOCKS_DEFAULT_SORT,
  });
}


// ── POST /api/stocks  →  insert one row ──────────────────────────
//
// Body shape:
//   { ticker: string,
//     close?: number, float_value?: number, short_percent_float?: number,
//     avg_month_volume?: number, shares_outstanding?: number,
//     shares_short?: number }
//
// `ticker` is required and is uppercased + trimmed before insert.
// Numeric fields are optional; missing values become NULL (except
// avg_month_volume which the schema declares NOT NULL DEFAULT 0).

const TICKER_PATTERN = /^[A-Z][A-Z0-9._\-]{0,9}$/;

function toNumberOrNull(v: unknown): number | null {
  if (v === null || v === undefined || v === "") return null;
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
}

export async function POST(req: NextRequest) {
  let body: Record<string, unknown>;
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ error: "Invalid JSON body" }, { status: 400 });
  }

  const ticker = String(body.ticker ?? "").trim().toUpperCase();
  if (!TICKER_PATTERN.test(ticker)) {
    return NextResponse.json(
      { error: "Ticker must be 1–10 chars, letters/digits/.- starting with a letter" },
      { status: 400 }
    );
  }

  try {
    const { insertId } = await execute(
      `INSERT INTO Stocks
         (ticker, close, float_value, short_percent_float,
          avg_month_volume, shares_outstanding, shares_short)
       VALUES (?, ?, ?, ?, ?, ?, ?)`,
      [
        ticker,
        toNumberOrNull(body.close),
        toNumberOrNull(body.float_value),
        toNumberOrNull(body.short_percent_float),
        toNumberOrNull(body.avg_month_volume) ?? 0,
        toNumberOrNull(body.shares_outstanding),
        toNumberOrNull(body.shares_short),
      ]
    );

    return NextResponse.json({ ok: true, id: insertId, ticker });
  } catch (err) {
    const message = err instanceof Error ? err.message : "Unknown error";
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
