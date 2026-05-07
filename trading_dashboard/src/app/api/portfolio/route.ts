import { NextRequest, NextResponse } from "next/server";
import { paginatedTableHandler } from "@/lib/handlers";
import { fetchLastTrades } from "@/lib/polygon";
import {
  PORTFOLIO_TABLE,
  PORTFOLIO_HELD_COLUMNS,
  PORTFOLIO_HELD_COLUMN_WHITELIST,
  PORTFOLIO_HELD_DEFAULT_SORT,
  dbColumnKeys,
} from "@/lib/tables";

// GET /api/portfolio
//
// Currently-HELD IB positions only (`sold_at IS NULL`). The matching
// /api/portfolio/sold route serves the historical sold rows.
//
// Each response is enriched with a virtual `last_price` field per row,
// fetched from Polygon's multi-ticker snapshot endpoint. The dashboard
// polls this route every 5 s, so the `Last` column refreshes at the
// same cadence — enough to tell whether each held position is moving
// up or down against its avg cost. Polygon failures fall through
// silently: `last_price` becomes null, the cell renders blank.
export async function GET(req: NextRequest) {
  const res = await paginatedTableHandler(req, {
    table: PORTFOLIO_TABLE,
    columnList: dbColumnKeys(PORTFOLIO_HELD_COLUMNS),
    columnWhitelist: PORTFOLIO_HELD_COLUMN_WHITELIST,
    defaultSort: PORTFOLIO_HELD_DEFAULT_SORT,
    extraWhere: "sold_at IS NULL",
  });

  if (res.status !== 200) return res;

  const body = (await res.json()) as { rows?: Array<Record<string, unknown>> } & Record<string, unknown>;
  const rows = body.rows ?? [];

  const symbols = rows
    .map((r) => (typeof r.symbol === "string" ? r.symbol : null))
    .filter((s): s is string => s !== null);

  const prices = await fetchLastTrades(symbols);
  for (const r of rows) {
    const sym = typeof r.symbol === "string" ? r.symbol.toUpperCase() : null;
    r.last_price = sym !== null && prices.has(sym) ? prices.get(sym)! : null;
  }

  return NextResponse.json({ ...body, rows });
}
