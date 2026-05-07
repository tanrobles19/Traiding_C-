// Spread aggregates over the FULL filtered set (not just one page).
// The QuotesSummaryPanel calls this to show worst / best / average
// computed in SQL across every row matching the active filters.

import { NextRequest } from "next/server";
import { query } from "@/lib/db";
import { buildWhere, parseFiltersParam } from "@/lib/query-builder";
import {
  RAW_QUOTES_COLUMN_WHITELIST,
  RAW_QUOTES_TABLE,
} from "@/lib/tables";

type AggregateRow = {
  worst: number | null;
  best: number | null;
  avg: number | string | null;
  count: number;
};

export async function GET(req: NextRequest) {
  try {
    const url = new URL(req.url);
    const filters = parseFiltersParam(url.searchParams.get("filters"));
    const where = buildWhere(filters, RAW_QUOTES_COLUMN_WHITELIST);

    const sql =
      `SELECT
         MAX(spread)   AS worst,
         MIN(spread)   AS best,
         AVG(spread)   AS avg,
         COUNT(spread) AS count
       FROM \`${RAW_QUOTES_TABLE}\`${where.sql}`;

    const rows = await query<AggregateRow>(sql, where.params);
    const r = rows[0] ?? { worst: null, best: null, avg: null, count: 0 };

    return Response.json({
      worst: r.worst === null ? null : Number(r.worst),
      best:  r.best  === null ? null : Number(r.best),
      avg:   r.avg   === null ? null : Number(r.avg),
      count: Number(r.count) || 0,
    });
  } catch (e) {
    return Response.json({ error: (e as Error).message }, { status: 400 });
  }
}
