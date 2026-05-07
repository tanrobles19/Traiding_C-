import { NextRequest, NextResponse } from "next/server";
import { query } from "@/lib/db";

// GET /api/raw-quotes/series?symbol=ERNA&limit=10000
//
// Returns chart-ready quote points for a single symbol, ordered by
// quote time:
//   { symbol, points: [{ t, spread, bid, ask, bid_sz, ask_sz }], stats: {...} }
//
// `t` is unix milliseconds (parsed from RawQuotes.unix_timestamp,
// which stores Polygon's quote timestamp in nanoseconds).
//
// `spread` comes straight from the column already computed by the
// download script (`ask - bid`). Negative spreads (crossed market)
// are kept rather than clamped — they're real microstructure events.

export async function GET(req: NextRequest) {
  const url = req.nextUrl;
  const symbol = (url.searchParams.get("symbol") ?? "").trim().toUpperCase();
  const limit = Math.min(50_000, Math.max(1, Number(url.searchParams.get("limit") ?? 10_000)));

  if (!symbol || !/^[A-Z][A-Z0-9.\-_]{0,9}$/.test(symbol)) {
    return NextResponse.json({ error: "Required query param: symbol (A-Z…)" }, { status: 400 });
  }

  try {
    const rows = await query<{
      unix_timestamp: string | number | null;
      timestamp:      string | null;
      bid_price:      string | number | null;
      ask_price:      string | number | null;
      bid_size:       number | null;
      ask_size:       number | null;
      spread:         string | number | null;
    }>(
      `SELECT unix_timestamp, timestamp, bid_price, ask_price, bid_size, ask_size, spread
       FROM RawQuotes
       WHERE symbol = ?
       ORDER BY id ASC
       LIMIT ?`,
      [symbol, limit],
    );

    if (rows.length === 0) {
      return NextResponse.json({ symbol, points: [], stats: { count: 0 } });
    }

    const points = rows.map((r) => {
      let t: number | null = null;
      if (r.unix_timestamp != null) {
        const ns = Number(r.unix_timestamp);
        if (Number.isFinite(ns)) t = ns / 1_000_000;
      }
      if (t == null && r.timestamp) {
        const parsed = Date.parse(r.timestamp);
        if (Number.isFinite(parsed)) t = parsed;
      }
      const spread = r.spread == null ? null : Number(r.spread);
      const bid    = r.bid_price == null ? null : Number(r.bid_price);
      const ask    = r.ask_price == null ? null : Number(r.ask_price);
      return {
        t,
        spread: Number.isFinite(spread as number) ? spread : null,
        bid:    Number.isFinite(bid as number) ? bid : null,
        ask:    Number.isFinite(ask as number) ? ask : null,
        bid_sz: r.bid_size ?? 0,
        ask_sz: r.ask_size ?? 0,
      };
    }).filter((p) => p.t != null && p.spread != null) as
      { t: number; spread: number; bid: number | null; ask: number | null; bid_sz: number; ask_sz: number }[];

    if (points.length === 0) {
      return NextResponse.json({ symbol, points: [], stats: { count: 0 } });
    }

    let minS = points[0].spread, maxS = points[0].spread;
    let sumS = 0;
    for (const p of points) {
      if (p.spread < minS) minS = p.spread;
      if (p.spread > maxS) maxS = p.spread;
      sumS += p.spread;
    }

    return NextResponse.json({
      symbol,
      points,
      stats: {
        count:      points.length,
        first_t:    points[0].t,
        last_t:     points[points.length - 1].t,
        min_spread: minS,
        max_spread: maxS,
        avg_spread: sumS / points.length,
        truncated:  rows.length === limit,
      },
    });
  } catch (err) {
    const message = err instanceof Error ? err.message : "Unknown error";
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
