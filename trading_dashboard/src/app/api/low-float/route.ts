import { NextRequest } from "next/server";
import { promises as fs } from "node:fs";
import path from "node:path";
import { paginatedTableHandler } from "@/lib/handlers";
import {
  LOW_FLOAT_TABLE,
  LOW_FLOAT_COLUMNS,
  LOW_FLOAT_COLUMN_WHITELIST,
  LOW_FLOAT_DEFAULT_SORT,
  LOW_FLOAT_MAX_VALUE_FALLBACK,
  dbColumnKeys,
  dbExpressionMap,
} from "@/lib/tables";

// GET /api/low-float
//
// Pre-filtered view of `Stocks` matching the low-float momentum
// strategy's universe. ALL filter values come from
// `../../trading_config.json` at request time, so dashboard edits via
// /api/config show up on the next refetch:
//
//   float_value > 0
//   AND float_value < trading_config.low_float_threshold
//   AND close >= trading_config.min_price
//   AND close <= trading_config.max_price
//
// Mirrors the legacy `get_low_float_stocks()` helper in get_float.py.
// LOW_FLOAT_MAX_VALUE_FALLBACK is used only when the JSON is missing
// the field (back-compat) — promote the JSON to the source of truth.

const CONFIG_PATH = path.resolve(process.cwd(), "..", "trading_config.json");

type Filters = { min: number; max: number; floatMax: number };

async function readFilters(): Promise<Filters> {
  try {
    const txt = await fs.readFile(CONFIG_PATH, "utf8");
    const cfg = JSON.parse(txt) as Record<string, unknown>;
    const min      = Number(cfg.min_price);
    const max      = Number(cfg.max_price);
    const floatMax = Number(cfg.low_float_threshold);
    return {
      min:      Number.isFinite(min)      ? min      : 1,
      max:      Number.isFinite(max)      ? max      : 5,
      floatMax: Number.isFinite(floatMax) ? floatMax : LOW_FLOAT_MAX_VALUE_FALLBACK,
    };
  } catch {
    // Fallback matches the Python defaults in trading_config.py.
    return { min: 1, max: 5, floatMax: LOW_FLOAT_MAX_VALUE_FALLBACK };
  }
}

export async function GET(req: NextRequest) {
  const { min, max, floatMax } = await readFilters();

  // ── ORIGINAL extraWhere (pre-2026-05-03) — preserved for rollback ──
  // const extraWhere =
  //   `float_value > 0 ` +
  //   `AND float_value < ${floatMax} ` +
  //   `AND close >= ${min} ` +
  //   `AND close <= ${max}`;

  // All four values are validated as finite numbers — safe to inline
  // into the SQL fragment. They never come from user input.
  //
  // SANITY GUARDS at the SQL level so rows with corrupted upstream data
  // never surface in the scanner, even if a Step 3 run hasn't yet nulled
  // them out:
  //
  //   - shares_outstanding > 0
  //     Ensures the multi-class / ADR rows where SO is 0 don't pass
  //     a check that depends on dividing by it.
  //
  //   - float_value <= shares_outstanding
  //     Float can never exceed Shares Outstanding (it's a subset).
  //
  //   - shares_short IS NULL OR shares_short <= shares_outstanding * 1.5
  //     Allows real naked-short outliers (Short ≈ SO, like RDGT) but
  //     blocks vendor bugs that produce Short ≫ SO.
  //
  // 2026-05-04: shares_short is now sourced from yfinance (was Polygon
  // Short Interest API, which had 10×/20×/25× bugs for some tickers —
  // VNRX, UP, RAYA, AIRE). yfinance's value matches Yahoo's website
  // exactly. The 1.5×SO ratio gate is kept as defense-in-depth against
  // any residual yfinance bugs (e.g. CMCT-style float scale errors).
  //
  // Same threshold as `SANITY_MAX_SHORT_TO_SO_RATIO` in get_float.py
  // — keep the two in sync if the value ever changes.
  const extraWhere =
    `float_value > 0 ` +
    `AND float_value < ${floatMax} ` +
    `AND close >= ${min} ` +
    `AND close <= ${max} ` +
    `AND shares_outstanding > 0 ` +
    `AND float_value <= shares_outstanding ` +
    `AND (shares_short IS NULL OR shares_short <= shares_outstanding * 1.5)`;

  return paginatedTableHandler(req, {
    table: LOW_FLOAT_TABLE,
    columnList: dbColumnKeys(LOW_FLOAT_COLUMNS),
    columnWhitelist: LOW_FLOAT_COLUMN_WHITELIST,
    defaultSort: LOW_FLOAT_DEFAULT_SORT,
    extraWhere,
    selectExpressions: dbExpressionMap(LOW_FLOAT_COLUMNS),
  });
}
