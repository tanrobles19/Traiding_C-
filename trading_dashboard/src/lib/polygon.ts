// Multi-ticker last-trade lookup against Polygon's snapshot endpoint.
//
// One outbound call per refresh — the snapshot endpoint returns the
// latest trade for every requested ticker in a single response, so
// /api/portfolio can enrich its 5-second poll with a single fetch
// regardless of how many positions the operator holds.
//
//   GET /v2/snapshot/locale/us/markets/stocks/tickers?tickers=AAA,BBB
//   →   { tickers: [ { ticker, lastTrade: { p: 12.34, ... } }, … ] }
//
// Returns Map<symbol, lastPrice>. Tickers that Polygon doesn't know
// about (delisted, weekend gap, …) are simply absent from the map —
// callers should treat that as "no price available" and render blank.

const POLYGON_BASE = "https://api.polygon.io";

// Hardcoded fallback mirrors the convention in db.ts. The key matches
// what the Python modules already use (see position_manager.py).
const API_KEY =
  process.env.POLYGON_API_KEY ?? "0oQUg6UgH34Ala4OF_YYObsT_5Jh2IBJ";

type SnapshotTicker = {
  ticker?: string;
  lastTrade?: { p?: number };
};

type SnapshotResponse = {
  tickers?: SnapshotTicker[];
};

export async function fetchLastTrades(
  symbols: string[]
): Promise<Map<string, number>> {
  const result = new Map<string, number>();
  if (symbols.length === 0) return result;

  const unique = Array.from(
    new Set(symbols.map((s) => s.toUpperCase()))
  );
  const url =
    `${POLYGON_BASE}/v2/snapshot/locale/us/markets/stocks/tickers` +
    `?tickers=${encodeURIComponent(unique.join(","))}` +
    `&apiKey=${encodeURIComponent(API_KEY)}`;

  let res: Response;
  try {
    res = await fetch(url, { cache: "no-store" });
  } catch {
    return result;
  }
  if (!res.ok) return result;

  const body = (await res.json().catch(() => null)) as SnapshotResponse | null;
  for (const t of body?.tickers ?? []) {
    const sym = t.ticker;
    const px = t.lastTrade?.p;
    if (typeof sym === "string" && typeof px === "number" && Number.isFinite(px)) {
      result.set(sym, px);
    }
  }
  return result;
}
