import mysql from "mysql2/promise";

// Single MySQL pool shared across all API route handlers.
// Lazily created on first call so module load is cheap and so dev hot-reload
// doesn't leak pools.
let pool: mysql.Pool | null = null;

export function getPool(): mysql.Pool {
  if (pool) return pool;

  // Local-only dashboard — credentials match the C++ trading system.
  // Dotenv mangles the `$` in the password, so we keep a hardcoded
  // fallback. If you ever deploy this, override via a real secret store.
  pool = mysql.createPool({
    host:     process.env.DB_HOST     ?? "localhost",
    port:     Number(process.env.DB_PORT ?? 3306),
    user:     process.env.DB_USER     ?? "root",
    password: process.env.DB_PASSWORD ?? "E_I$S5PFri",
    database: process.env.DB_NAME     ?? "histFinanData",
    connectionLimit: 5,
    waitForConnections: true,
    namedPlaceholders: true,
  });

  return pool;
}

// Run a parameterized SELECT and return rows.
export async function query<T = Record<string, unknown>>(
  sql: string,
  params: unknown[] = []
): Promise<T[]> {
  const [rows] = await getPool().query(sql, params);
  return rows as T[];
}

// Run a single COUNT(*) query and return the integer.
export async function count(
  sql: string,
  params: unknown[] = []
): Promise<number> {
  const rows = await query<{ n: number | string }>(sql, params);
  if (rows.length === 0) return 0;
  return Number(rows[0].n);
}

// Run a write statement (INSERT / DELETE / TRUNCATE) and return how
// many rows it affected. Used by the small set of mutating endpoints
// (add/remove stock, clear signals, clear orders).
//
// We use `query` rather than `execute` because mysql2's typed `execute`
// doesn't accept `null` in its parameter array, even though the driver
// supports it. `query` is parameterized the same way at the wire level.
export type SqlValue = string | number | boolean | null;

export async function execute(
  sql: string,
  params: SqlValue[] = []
): Promise<{ affectedRows: number; insertId: number }> {
  const [result] = await getPool().query(sql, params);
  // mysql2 returns ResultSetHeader for non-SELECTs
  const r = result as { affectedRows?: number; insertId?: number };
  return {
    affectedRows: r.affectedRows ?? 0,
    insertId:     r.insertId ?? 0,
  };
}
