import { NextRequest, NextResponse } from "next/server";
import { count, query } from "@/lib/db";
import {
  buildLimit,
  buildOrderBy,
  buildWhere,
  parseFiltersParam,
  parseSortParam,
} from "@/lib/query-builder";

type HandlerOptions = {
  table: string;
  columnList: string[];
  columnWhitelist: ReadonlySet<string>;
  defaultSort: { column: string; dir: "asc" | "desc" };
  // Hardcoded SQL fragment AND'd into the WHERE clause. Trusted —
  // developer-written, never user input. Used to permanently scope
  // a route to a slice of the table (e.g. /api/portfolio → held only,
  // /api/portfolio/sold → sold only).
  extraWhere?: string;
  // Per-key SQL expressions for server-side computed columns. When a
  // key in `columnList` has an entry here, the SELECT emits
  // `(expression) AS \`key\`` instead of the plain backticked column.
  // The alias is sortable (MySQL accepts aliases in ORDER BY) but not
  // filterable (aliases don't work in WHERE — DataGrid disables the
  // floating filter for these columns). Trusted SQL — built from
  // ColumnDef.dbExpression, never from user input.
  selectExpressions?: Record<string, string>;
};

// Shared paginated handler used by both /api/signals and /api/orders.
// Keeps the route files trivial and the SQL safety logic in one place.
export async function paginatedTableHandler(
  req: NextRequest,
  opts: HandlerOptions
): Promise<NextResponse> {
  const url = req.nextUrl;

  const page     = Number(url.searchParams.get("page")     ?? 0);
  const pageSize = Number(url.searchParams.get("pageSize") ?? 100);
  const filters  = parseFiltersParam(url.searchParams.get("filters"));
  const sort     = parseSortParam(url.searchParams.get("sort")) ?? opts.defaultSort;

  try {
    const where = buildWhere(filters, opts.columnWhitelist);
    const fullWhere = opts.extraWhere
      ? (where.sql
          ? `${where.sql} AND (${opts.extraWhere})`
          : ` WHERE (${opts.extraWhere})`)
      : where.sql;
    const orderBy = buildOrderBy(sort, opts.columnWhitelist, opts.defaultSort.column, opts.defaultSort.dir);
    const limit = buildLimit(page, pageSize);

    const colList = opts.columnList
      .map((c) => {
        const expr = opts.selectExpressions?.[c];
        return expr ? `(${expr}) AS \`${c}\`` : `\`${c}\``;
      })
      .join(", ");

    const rowsSql  = `SELECT ${colList} FROM \`${opts.table}\`${fullWhere}${orderBy}${limit}`;
    const countSql = `SELECT COUNT(*) AS n FROM \`${opts.table}\`${fullWhere}`;

    const [rows, total] = await Promise.all([
      query(rowsSql, where.params),
      count(countSql, where.params),
    ]);

    return NextResponse.json({
      rows,
      total,
      page,
      pageSize,
      sort,
      filters,
    });
  } catch (err) {
    const message = err instanceof Error ? err.message : "Unknown error";
    return NextResponse.json({ error: message }, { status: 400 });
  }
}
