import { NextRequest, NextResponse } from "next/server";
import { count, query } from "@/lib/db";
import {
  buildLimit,
  buildOrderBy,
  buildWhere,
  parseFiltersParam,
  parseSortParam,
} from "@/lib/query-builder";
import {
  SIGNALS_COLUMNS,
  SIGNALS_COLUMN_WHITELIST,
  SIGNALS_DEFAULT_SORT,
  SIGNALS_TABLE,
  dbColumnKeys,
} from "@/lib/tables";

// Custom handler (vs the shared paginatedTableHandler) so we can
// enrich BUY signals with whether they ended in a Filled order.
// Each row gets a boolean `was_filled` — true when there exists an
// Orders row with status='Filled' for the same symbol within ±1 s
// of the signal's `timestamp`. The dashboard uses this to render a
// green check next to "BUY" so the operator sees at a glance which
// BUYs actually went through.
//
// Why not a SQL JOIN? Two reasons:
//   (1) The signals table doesn't have a foreign key into Orders,
//       so the match has to be done by (symbol, timestamp tolerance).
//   (2) JOINing across two large tables on a non-indexed temporal
//       window is expensive; doing it as a small post-fetch lookup
//       on the page (≤ 100 rows) keeps the cost bounded regardless
//       of total table size.
export async function GET(req: NextRequest) {
  const url = req.nextUrl;
  const page     = Number(url.searchParams.get("page")     ?? 0);
  const pageSize = Number(url.searchParams.get("pageSize") ?? 100);
  const filters  = parseFiltersParam(url.searchParams.get("filters"));
  const sort     = parseSortParam(url.searchParams.get("sort")) ?? SIGNALS_DEFAULT_SORT;

  try {
    const where   = buildWhere(filters, SIGNALS_COLUMN_WHITELIST);
    const orderBy = buildOrderBy(sort, SIGNALS_COLUMN_WHITELIST,
                                 SIGNALS_DEFAULT_SORT.column,
                                 SIGNALS_DEFAULT_SORT.dir);
    const limit   = buildLimit(page, pageSize);

    const colList = dbColumnKeys(SIGNALS_COLUMNS).map((c) => `\`${c}\``).join(", ");

    const rowsSql  = `SELECT ${colList} FROM \`${SIGNALS_TABLE}\`${where.sql}${orderBy}${limit}`;
    const countSql = `SELECT COUNT(*) AS n FROM \`${SIGNALS_TABLE}\`${where.sql}`;

    const [rowsRaw, total] = await Promise.all([
      query<Record<string, unknown>>(rowsSql, where.params),
      count(countSql, where.params),
    ]);

    // ── Enrich BUY rows with was_filled ─────────────────────────
    // Pull the distinct symbols of the BUY rows on this page, then
    // ask Orders for any Filled rows for those symbols. The match
    // is (symbol, |order.start_timestamp − signal.timestamp| < 1 s).
    const buys = rowsRaw.filter((r) => r.purchasePrediction === "BUY");
    const buySymbols = Array.from(new Set(buys.map((r) => String(r.symbol))));

    let filledOrders: { symbol: string; start_timestamp: string }[] = [];
    if (buySymbols.length > 0) {
      const placeholders = buySymbols.map(() => "?").join(",");
      filledOrders = await query<{ symbol: string; start_timestamp: string }>(
        `SELECT symbol, start_timestamp
           FROM Orders
          WHERE status = 'Filled'
            AND symbol IN (${placeholders})`,
        buySymbols
      );
    }

    // Index Filled orders by symbol for an O(N+M) match instead of O(N*M).
    const filledBySymbol = new Map<string, number[]>();
    for (const o of filledOrders) {
      const arr = filledBySymbol.get(o.symbol) ?? [];
      arr.push(Number(o.start_timestamp));
      filledBySymbol.set(o.symbol, arr);
    }

    const TOLERANCE_SEC = 1;
    const rows = rowsRaw.map((r) => {
      let was_filled = false;
      if (r.purchasePrediction === "BUY") {
        const sigTs = Number(r.timestamp);
        const candidates = filledBySymbol.get(String(r.symbol)) ?? [];
        for (const orderTs of candidates) {
          if (Math.abs(orderTs - sigTs) <= TOLERANCE_SEC) {
            was_filled = true;
            break;
          }
        }
      }
      return { ...r, was_filled };
    });

    return NextResponse.json({ rows, total, page, pageSize, sort, filters });
  } catch (err) {
    const message = err instanceof Error ? err.message : "Unknown error";
    return NextResponse.json({ error: message }, { status: 400 });
  }
}
