import { NextRequest, NextResponse } from "next/server";
import { promises as fs } from "node:fs";
import path from "node:path";
import { query } from "@/lib/db";

// GET /api/raw-trades/series?symbol=CPIX&limit=10000
//
// Returns chart-ready points for a single symbol, ordered by tick time:
//   { symbol, points: [{ t, price, volume }], stats: {...} }
//
// `t` is unix milliseconds (parsed from `transactions`, which stores the
// Polygon participant_timestamp in nanoseconds — the most precise time
// we have for a tick).
//
// `limit` caps the number of rows returned. Default 10,000. The grid
// page already has full pagination; this endpoint is purely for charts,
// so very large series should be downsampled before plotting.
//
// Filter (added 2026-05-06): only ticks with `volume >= min_trade_size`
// are returned. The threshold comes from `../trading_config.json` —
// same value the C++ trader uses for OHLC gating. This keeps the chart
// focused on meaningful trades and skips odd-lot noise.

const CONFIG_PATH = path.resolve(process.cwd(), "..", "trading_config.json");

async function readMinTradeSize(): Promise<number> {
  try {
    const raw = await fs.readFile(CONFIG_PATH, "utf8");
    const cfg = JSON.parse(raw) as Record<string, unknown>;
    const v = Number(cfg.min_trade_size);
    return Number.isFinite(v) && v > 0 ? v : 100;
  } catch {
    return 100;
  }
}

export async function GET(req: NextRequest) {
  const url = req.nextUrl;
  const symbol = (url.searchParams.get("symbol") ?? "").trim().toUpperCase();
  const limit = Math.min(50_000, Math.max(1, Number(url.searchParams.get("limit") ?? 10_000)));

  if (!symbol || !/^[A-Z][A-Z0-9.\-_]{0,9}$/.test(symbol)) {
    return NextResponse.json({ error: "Required query param: symbol (A-Z…)" }, { status: 400 });
  }

  const minTradeSize = await readMinTradeSize();

  try {
    const rows = await query<{
      transactions: string | number | null;
      timestamp:    string | null;
      close:        string | number | null;
      volume:       number | null;
    }>(
      `SELECT transactions, timestamp, close, volume
       FROM RawTrades
       WHERE symbol = ?
         AND volume >= ?
       ORDER BY id ASC
       LIMIT ?`,
      [symbol, minTradeSize, limit],
    );

    if (rows.length === 0) {
      return NextResponse.json({
        symbol,
        points: [],
        stats: { min_trade_size: minTradeSize, count: 0 },
      });
    }

    // Map rows → chart points. Convert ns → ms; fall back to ISO timestamp
    // parse if the ns column is missing.
    const points = rows.map((r) => {
      let t: number | null = null;
      if (r.transactions != null) {
        // mysql2 returns BIGINT as a string by default — parse via Number,
        // then divide. JS number is fine for ns→ms (ms fits in 53 bits well
        // beyond year 9999).
        const ns = Number(r.transactions);
        if (Number.isFinite(ns)) t = ns / 1_000_000;
      }
      if (t == null && r.timestamp) {
        const parsed = Date.parse(r.timestamp);
        if (Number.isFinite(parsed)) t = parsed;
      }
      const price = r.close == null ? null : Number(r.close);
      return {
        t,
        price: Number.isFinite(price as number) ? price : null,
        volume: r.volume == null ? 0 : Number(r.volume),
      };
    }).filter((p) => p.t != null && p.price != null) as { t: number; price: number; volume: number }[];

    if (points.length === 0) {
      return NextResponse.json({ symbol, points: [], stats: null });
    }

    let minP = points[0].price, maxP = points[0].price;
    let totalVolume = 0;
    for (const p of points) {
      if (p.price < minP) minP = p.price;
      if (p.price > maxP) maxP = p.price;
      totalVolume += p.volume;
    }

    return NextResponse.json({
      symbol,
      points,
      stats: {
        count:        points.length,
        first_t:      points[0].t,
        last_t:       points[points.length - 1].t,
        min_price:    minP,
        max_price:    maxP,
        first_price:  points[0].price,
        last_price:   points[points.length - 1].price,
        total_volume: totalVolume,
        truncated:    rows.length === limit,
        min_trade_size: minTradeSize,
      },
    });
  } catch (err) {
    const message = err instanceof Error ? err.message : "Unknown error";
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
