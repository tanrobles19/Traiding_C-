// GET /api/signal-latency
//
// Pulls every row from TradeSignalsBuyPerSecond and aggregates the
// `local_utc_timestamp` column — that's the transport latency
// (arrival_ms − sip_ms) the dashboard surfaces as "Latency (ms)".
// Returns headline stats, the top latency peaks (with symbol + time
// of occurrence), and a time-ordered series for charting.

import { NextResponse } from "next/server";
import { query } from "@/lib/db";

type Row = {
  symbol:     string;
  latency_ms: number | string | null;
  ts:         number | string | null;   // unix seconds (DOUBLE)
};

function n(v: number | string | null | undefined): number {
  if (v === null || v === undefined) return NaN;
  const x = typeof v === "string" ? Number(v) : v;
  return Number.isFinite(x) ? x : NaN;
}

function percentile(sortedAsc: number[], p: number): number {
  if (sortedAsc.length === 0) return 0;
  const idx = Math.min(sortedAsc.length - 1, Math.floor((sortedAsc.length * p) / 100));
  return sortedAsc[idx];
}

// Render a unix-seconds value as an ISO-shaped string in Costa Rica
// local time (matching the format already used by the C++ summary
// CSV — no Z, no offset). sv-SE locale gives "YYYY-MM-DD HH:MM:SS",
// then the space gets swapped to a T so the page's HH:MM:SS regex
// extractor still works for both data sources.
const CR_FORMATTER = new Intl.DateTimeFormat("sv-SE", {
  timeZone: "America/Costa_Rica",
  year: "numeric", month: "2-digit", day: "2-digit",
  hour: "2-digit", minute: "2-digit", second: "2-digit",
  hour12: false,
  fractionalSecondDigits: 3,
});

function isoFromUnixSeconds(s: number): string {
  return CR_FORMATTER.format(new Date(s * 1000)).replace(" ", "T");
}

export async function GET() {
  try {
    const rows = await query<Row>(
      `SELECT symbol,
              local_utc_timestamp AS latency_ms,
              timestamp           AS ts
         FROM TradeSignalsBuyPerSecond
         WHERE local_utc_timestamp IS NOT NULL
         ORDER BY timestamp ASC`
    );

    // Filter to numeric, valid rows. Drop NaNs and negatives — a
    // negative latency would mean the local clock is ahead of the SIP
    // clock, almost certainly a bad sample we don't want skewing avg.
    const clean = rows
      .map((r) => ({
        symbol:     r.symbol,
        latency_ms: n(r.latency_ms),
        ts_sec:     n(r.ts),
      }))
      .filter((r) => Number.isFinite(r.latency_ms) && r.latency_ms >= 0 && Number.isFinite(r.ts_sec));

    if (clean.length === 0) {
      return NextResponse.json({
        count: 0,
        message: "No signals with latency data yet.",
      });
    }

    const latencies = clean.map((r) => r.latency_ms);
    const sorted    = [...latencies].sort((a, b) => a - b);
    const sum       = latencies.reduce((s, x) => s + x, 0);
    const avg       = sum / latencies.length;
    const max       = sorted[sorted.length - 1];
    const min       = sorted[0];

    // Sort by latency desc → take top 10 peaks. Snapshot WHEN each
    // peak fired (`ts` → ISO) so the dashboard can show "the worst
    // latency was 25 s, on TKNO at 08:31:38".
    const topPeaks = [...clean]
      .sort((a, b) => b.latency_ms - a.latency_ms)
      .slice(0, 10)
      .map((r) => ({
        symbol:     r.symbol,
        latency_ms: r.latency_ms,
        iso:        isoFromUnixSeconds(r.ts_sec),
      }));

    // Time-ordered series for the chart. Cap at ~3 K points so the
    // payload stays small on long sessions; older points get dropped
    // first since the user is most interested in the recent shape.
    const SERIES_CAP = 3000;
    const series = clean
      .slice(-SERIES_CAP)
      .map((r) => ({
        iso:        isoFromUnixSeconds(r.ts_sec),
        symbol:     r.symbol,
        latency_ms: r.latency_ms,
      }));

    return NextResponse.json({
      count: latencies.length,
      stats: {
        avg_ms: Math.round(avg),
        p50_ms: Math.round(percentile(sorted, 50)),
        p95_ms: Math.round(percentile(sorted, 95)),
        p99_ms: Math.round(percentile(sorted, 99)),
        min_ms: min,
        max_ms: max,
      },
      peak: topPeaks[0],
      top_peaks: topPeaks,
      series,
    });
  } catch (err) {
    const message = err instanceof Error ? err.message : "Unknown error";
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
