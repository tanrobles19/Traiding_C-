// /api/config — GET + PUT for ../../trading_config.json
//
// Single source of truth shared with the C++ trader (which reads the
// same file at startup, see cpp_ultra_low_latency/trading_config.h).
// PUT validates field types and writes atomically (write to .tmp,
// rename) so a crashed dashboard can never leave a partial JSON the
// trader would fail to parse.

import { NextRequest, NextResponse } from "next/server";
import { promises as fs } from "node:fs";
import path from "node:path";

// trading_config.json sits at the repo root, two levels up from the
// dashboard's package.json. process.cwd() is the dashboard directory
// when `npm run dev` runs.
const CONFIG_PATH = path.resolve(process.cwd(), "..", "trading_config.json");

// Whitelist of writable fields plus their TS types. Anything else in
// the request body is silently ignored. Anything in the file that's
// not in this list (e.g. _comment) is preserved across writes.
const FIELDS = {
  relative_volume_factor:   "number",
  increase_from_open_pct:   "number",
  min_trade_size:           "number",
  low_activity_threshold:   "number",
  order_quantity:           "number",
  float_threshold:          "number",
  low_float_threshold:      "number",
  min_price:                "number",
  max_price:                "number",
  trade_capital:            "number",
  max_loss_tolerance_pct:   "number",
  historical_days:          "number",
  max_spread_abs:           "number",
} as const;

type FieldName = keyof typeof FIELDS;

async function readConfig(): Promise<Record<string, unknown>> {
  const txt = await fs.readFile(CONFIG_PATH, "utf8");
  return JSON.parse(txt);
}

export async function GET() {
  try {
    const cfg = await readConfig();
    return NextResponse.json(cfg);
  } catch (err) {
    return NextResponse.json(
      { error: `Failed to read trading_config.json: ${(err as Error).message}` },
      { status: 500 }
    );
  }
}

export async function PUT(req: NextRequest) {
  let body: Record<string, unknown>;
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ error: "Invalid JSON body" }, { status: 400 });
  }

  // Validate: every supplied field must be in the whitelist AND match
  // its expected type. Reject the whole request on any mismatch — we'd
  // rather refuse than write a half-good file the trader will reject.
  const validated: Record<string, number> = {};
  for (const [key, value] of Object.entries(body)) {
    if (!(key in FIELDS)) {
      return NextResponse.json(
        { error: `Unknown field: ${key}` },
        { status: 400 }
      );
    }
    if (typeof value !== "number" || !Number.isFinite(value)) {
      return NextResponse.json(
        { error: `Field '${key}' must be a finite number` },
        { status: 400 }
      );
    }
    validated[key] = value;
  }

  // Merge with existing file so unknown keys (_comment, future fields)
  // are preserved. Then write atomically.
  let current: Record<string, unknown> = {};
  try {
    current = await readConfig();
  } catch {
    // File missing or malformed — start fresh; PUT effectively recreates it.
  }
  const merged = { ...current, ...validated };

  const tmpPath = CONFIG_PATH + ".tmp";
  try {
    await fs.writeFile(tmpPath, JSON.stringify(merged, null, 2) + "\n", "utf8");
    await fs.rename(tmpPath, CONFIG_PATH);
  } catch (err) {
    return NextResponse.json(
      { error: `Failed to write config: ${(err as Error).message}` },
      { status: 500 }
    );
  }

  return NextResponse.json({ ok: true, config: merged });
}

// Touch the FieldName type so TS doesn't drop it from the build output
// when the route is tree-shaken — keeps the field whitelist visible to
// future readers of this file.
export type _ConfigField = FieldName;
