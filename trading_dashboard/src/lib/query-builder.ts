// Tiny query builder for AG Grid server-side row model.
// Translates page/sort/filter params into SQL fragments.
// All values are parameterized — never concatenated into the SQL string.

export type SortDir = "asc" | "desc";

export type Filter = {
  column: string;
  op: "eq" | "ne" | "lt" | "le" | "gt" | "ge" | "contains" | "starts" | "ends";
  value: string | number;
};

export type QueryParams = {
  page: number;        // 0-based
  pageSize: number;    // rows per page
  sort?: { column: string; dir: SortDir };
  filters?: Filter[];
};

// Whitelisted columns per table. Anything not in here is rejected to
// prevent SQL injection through column-name parameters (which can't be
// parameterized via ?-placeholders).
export type ColumnWhitelist = ReadonlySet<string>;

function assertColumn(name: string, allowed: ColumnWhitelist) {
  if (!allowed.has(name)) {
    throw new Error(`Disallowed column: ${name}`);
  }
}

const OP_TO_SQL: Record<Filter["op"], (col: string) => string> = {
  eq:       (c) => `\`${c}\` = ?`,
  ne:       (c) => `\`${c}\` <> ?`,
  lt:       (c) => `\`${c}\` < ?`,
  le:       (c) => `\`${c}\` <= ?`,
  gt:       (c) => `\`${c}\` > ?`,
  ge:       (c) => `\`${c}\` >= ?`,
  contains: (c) => `\`${c}\` LIKE ?`,
  starts:   (c) => `\`${c}\` LIKE ?`,
  ends:     (c) => `\`${c}\` LIKE ?`,
};

function valueForOp(op: Filter["op"], value: string | number): string | number {
  switch (op) {
    case "contains": return `%${value}%`;
    case "starts":   return `${value}%`;
    case "ends":     return `%${value}`;
    default:         return value;
  }
}

export function buildWhere(filters: Filter[] | undefined, allowed: ColumnWhitelist): {
  sql: string;
  params: (string | number)[];
} {
  if (!filters || filters.length === 0) return { sql: "", params: [] };

  const clauses: string[] = [];
  const params: (string | number)[] = [];

  for (const f of filters) {
    assertColumn(f.column, allowed);
    clauses.push(OP_TO_SQL[f.op](f.column));
    params.push(valueForOp(f.op, f.value));
  }

  return { sql: ` WHERE ${clauses.join(" AND ")}`, params };
}

export function buildOrderBy(
  sort: QueryParams["sort"],
  allowed: ColumnWhitelist,
  fallbackColumn: string,
  fallbackDir: SortDir = "desc"
): string {
  if (!sort) return ` ORDER BY \`${fallbackColumn}\` ${fallbackDir.toUpperCase()}`;
  assertColumn(sort.column, allowed);
  const dir = sort.dir === "asc" ? "ASC" : "DESC";
  return ` ORDER BY \`${sort.column}\` ${dir}`;
}

export function buildLimit(page: number, pageSize: number): string {
  // Bound pageSize to a sane max so a malformed request can't return
  // millions of rows. 50K matches PAGE_SIZE_ALL in components/Pagination
  // — high enough that "All" works for any single-day Raw Trades
  // download (a few thousand ticks at most), but not unbounded.
  const safePageSize = Math.min(Math.max(pageSize, 1), 50_000);
  const safePage = Math.max(page, 0);
  const offset = safePage * safePageSize;
  return ` LIMIT ${safePageSize} OFFSET ${offset}`;
}

// Parse the JSON-encoded `filters` query-string param.
// Returns [] for missing / empty / invalid input rather than throwing.
export function parseFiltersParam(raw: string | null): Filter[] {
  if (!raw) return [];
  try {
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed.filter(
      (f) =>
        typeof f === "object" &&
        f !== null &&
        typeof f.column === "string" &&
        typeof f.op === "string" &&
        f.op in OP_TO_SQL &&
        (typeof f.value === "string" || typeof f.value === "number")
    );
  } catch {
    return [];
  }
}

export function parseSortParam(raw: string | null): QueryParams["sort"] {
  if (!raw) return undefined;
  try {
    const parsed = JSON.parse(raw);
    if (
      typeof parsed === "object" &&
      parsed !== null &&
      typeof parsed.column === "string" &&
      (parsed.dir === "asc" || parsed.dir === "desc")
    ) {
      return parsed;
    }
  } catch {
    /* fall through */
  }
  return undefined;
}
