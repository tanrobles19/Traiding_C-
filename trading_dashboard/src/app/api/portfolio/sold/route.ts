import { NextRequest } from "next/server";
import { paginatedTableHandler } from "@/lib/handlers";
import {
  PORTFOLIO_TABLE,
  PORTFOLIO_SOLD_COLUMNS,
  PORTFOLIO_SOLD_COLUMN_WHITELIST,
  PORTFOLIO_SOLD_DEFAULT_SORT,
  dbColumnKeys,
} from "@/lib/tables";

// GET /api/portfolio/sold
//
// Historical SOLD rows from the Portfolio table (`sold_at IS NOT NULL`).
// Returned as-is — no Polygon enrichment, no live `last_price`. These
// are exited positions; the relevant exit price is already in
// `sold_reason` ("STOP_LOSS @ -5.09% (cost=0.4704 tick=0.4465)").
//
// The dashboard fetches this route ONCE on mount (no polling) and
// renders it as a frozen table beneath the live Held grid.
export async function GET(req: NextRequest) {
  return paginatedTableHandler(req, {
    table: PORTFOLIO_TABLE,
    columnList: dbColumnKeys(PORTFOLIO_SOLD_COLUMNS),
    columnWhitelist: PORTFOLIO_SOLD_COLUMN_WHITELIST,
    defaultSort: PORTFOLIO_SOLD_DEFAULT_SORT,
    extraWhere: "sold_at IS NOT NULL",
  });
}
