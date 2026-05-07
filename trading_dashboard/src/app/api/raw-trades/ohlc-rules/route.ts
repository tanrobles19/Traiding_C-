import { NextResponse } from "next/server";
import { promises as fs } from "node:fs";
import path from "node:path";

// GET /api/raw-trades/ohlc-rules
//
// Returns the rules the C++ trader uses to decide which ticks update
// each candle component (open/close/high/low/volume), so the dashboard
// can replicate the same selection client-side and highlight the
// specific RawTrades rows that determined a minute's OHLC.
//
// Two inputs:
//   1. ../trading_config.json  →  min_trade_size (≥100 gate for HL/Vol).
//   2. ../polygon_conditions_trade_stocks.csv  →  per-condition booleans:
//        updates_open_close, updates_high_low, updates_volume.
//
// The C++ matching code lives at trade_processor.h:580-589
// (`condition_allows`) and trade_processor.h:861-895 (the OHLC update
// blocks). Keep the two in sync: the gate is "all conditions on a
// trade must permit the component, OR the trade has no conditions".

const CONFIG_PATH = path.resolve(process.cwd(), "..", "trading_config.json");
const CSV_PATH    = path.resolve(process.cwd(), "..", "polygon_conditions_trade_stocks.csv");

type ConditionRule = {
  oc:  boolean;
  hl:  boolean;
  vol: boolean;
};

type Response = {
  minTradeSize: number;
  // 2026-05-05 — surfaced for the per-row "Low activity" badge in the
  // /raw-trades page. Mirrors C++ passes_activity_check threshold:
  // `active > elapsed * lowActivityThreshold`.
  lowActivityThreshold: number;
  // Map keyed by condition id (1-based per Polygon SIP), value is the
  // three-component permission triple. Conditions not in this map are
  // treated as "deny" by the C++ trader (line 585 — unknown id → false).
  conditions: Record<string, ConditionRule>;
};

function parseBool(s: string): boolean {
  return s.trim().toLowerCase() === "true";
}

export async function GET() {
  let minTradeSize = 100;
  let lowActivityThreshold = 0.33;
  try {
    const rawCfg = await fs.readFile(CONFIG_PATH, "utf8");
    const cfg = JSON.parse(rawCfg) as Record<string, unknown>;
    const v = Number(cfg.min_trade_size);
    if (Number.isFinite(v) && v > 0) minTradeSize = v;
    const t = Number(cfg.low_activity_threshold);
    if (Number.isFinite(t) && t > 0 && t < 1) lowActivityThreshold = t;
  } catch {
    // fall through with defaults — match the C++ defaults in
    // trading_config.h.
  }

  const conditions: Record<string, ConditionRule> = {};
  try {
    const rawCsv = await fs.readFile(CSV_PATH, "utf8");
    const lines = rawCsv.split(/\r?\n/);
    // Header: id,name,abbreviation,description,updates_open_close,updates_high_low,updates_volume
    for (let i = 1; i < lines.length; i++) {
      const line = lines[i].trim();
      if (!line) continue;
      // Naive split is fine — the CSV has no quoted commas in the
      // first 4 columns (verified). Last 3 columns are bare True/False.
      const cols = line.split(",");
      if (cols.length < 7) continue;
      const id = cols[0].trim();
      if (!id) continue;
      conditions[id] = {
        oc:  parseBool(cols[cols.length - 3]),
        hl:  parseBool(cols[cols.length - 2]),
        vol: parseBool(cols[cols.length - 1]),
      };
    }
  } catch (err) {
    return NextResponse.json(
      { error: `Failed to load conditions CSV: ${err instanceof Error ? err.message : String(err)}` },
      { status: 500 }
    );
  }

  const body: Response = { minTradeSize, lowActivityThreshold, conditions };
  return NextResponse.json(body);
}
