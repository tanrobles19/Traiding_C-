// GET /api/run-status
//
// Reads the newest run CSV in the C++ trader's logs/ directory and
// returns aggregated telemetry plus a per-tick series for charting.
// The C++ summary_logger writes one row every 5 seconds; this route is
// the only consumer for the new System Status page.

import { NextResponse } from "next/server";
import { readdirSync, readFileSync, statSync } from "node:fs";
import path from "node:path";

const LOGS_DIR = path.resolve(
  process.cwd(),
  "..",
  "cpp_ultra_low_latency",
  "logs"
);

// Columns written by summary_logger.h (29, in order). Keep this in
// sync with cpp_ultra_low_latency/summary_logger.h::write_row().
//
// The last 5 are peaks tracked between ticks — these are the
// diagnostics that catch sub-5-s bursts the snapshot columns miss.
// See cpp_ultra_low_latency/CLAUDE.md, "Peak tracking" subsection.
const COLUMNS = [
  "timestamp_iso", "trades_received", "avg_parse_ns", "avg_process_ns",
  "cpu_pct", "latency_fresh", "sip_latency_ms", "exchange_latency_ms",
  "ring_depth", "ring_capacity", "ring_dropped",
  "kernel_recvq_bytes", "kernel_recvbuf_bytes", "tcp_rcv_wnd_bytes",
  "ws_messages_pushed", "ws_text", "ws_ping", "ws_pong", "ws_other",
  "ssl_read_calls", "ssl_read_bytes",
  "last_symbol", "last_price", "last_size",
  // Peaks added 2026-05-01:
  "ring_depth_max", "recvq_max_bytes", "rcv_wnd_min_bytes",
  "rcv_wnd_zero_count", "ring_dropped_delta",
  // Phase 2 (2026-05-06) — cumulative Q.* count.
  "quotes_received",
] as const;

type Row = Record<(typeof COLUMNS)[number], string>;

type Health = "green" | "yellow" | "red";

function pickNewestCsv(): string | null {
  let entries: string[];
  try {
    entries = readdirSync(LOGS_DIR);
  } catch {
    return null;
  }
  const csvs = entries
    .filter((n) => n.startsWith("run_") && n.endsWith(".csv"))
    .sort();             // filename embeds the timestamp → lexicographic = chronological
  return csvs.length === 0 ? null : path.join(LOGS_DIR, csvs[csvs.length - 1]);
}

// Minimum number of cells we accept — corresponds to the original
// 24-column schema. CSVs written before the peak-tracking change
// (2026-05-01) have only 24 cells per row; the extra 5 columns
// default to "0" so the rest of the route still works on legacy
// logs without crashing. Drop rows with fewer cells (truncated /
// torn writes).
const MIN_CELLS = 24;

function parseCsv(text: string): Row[] {
  const lines = text.split("\n").filter((l) => l.trim().length > 0);
  if (lines.length < 2) return [];
  // Trust the header order — we already know the schema. Skip line 0.
  const out: Row[] = [];
  for (let i = 1; i < lines.length; i++) {
    const cells = lines[i].split(",");
    if (cells.length < MIN_CELLS) continue;
    const r = {} as Row;
    for (let c = 0; c < COLUMNS.length; c++) {
      r[COLUMNS[c]] = c < cells.length ? cells[c] : "0";
    }
    out.push(r);
  }
  return out;
}

function n(v: string): number {
  const x = Number(v);
  return Number.isFinite(x) ? x : 0;
}

function percentile(sorted: number[], p: number): number {
  if (sorted.length === 0) return 0;
  const idx = Math.min(sorted.length - 1, Math.floor((sorted.length * p) / 100));
  return sorted[idx];
}

function avg(xs: number[]): number {
  if (xs.length === 0) return 0;
  let s = 0;
  for (const x of xs) s += x;
  return s / xs.length;
}

function maxOf(xs: number[]): number {
  if (xs.length === 0) return 0;
  let m = -Infinity;
  for (const x of xs) if (x > m) m = x;
  return m;
}

function minOf(xs: number[]): number {
  if (xs.length === 0) return 0;
  let m = Infinity;
  for (const x of xs) if (x < m) m = x;
  return m;
}

// ── Status thresholds ───────────────────────────────────────────
// Calibrated from typical C++ trader runs:
//   latency: < 200 ms healthy, < 1 s degraded, > 1 s lagging
//   ring:    depth as % of capacity — < 25 % fine, < 50 % busy, > 50 % overloaded
//   cpu:     processor thread is single-core; > 80 % means we're maxing out
//   drops:   anything > 0 means data was lost, that's red
//   bp:      a single tcp_rcv_wnd=0 sample means we paused Polygon → red

function classifyLatency(avgMs: number): Health {
  if (avgMs < 200)  return "green";
  if (avgMs < 1000) return "yellow";
  return "red";
}
function classifyRing(maxPct: number): Health {
  if (maxPct < 25) return "green";
  if (maxPct < 50) return "yellow";
  return "red";
}
function classifyCpu(maxPct: number): Health {
  if (maxPct < 50) return "green";
  if (maxPct < 80) return "yellow";
  return "red";
}
function classifyBool(any: boolean): Health {
  return any ? "red" : "green";
}

export async function GET() {
  const file = pickNewestCsv();
  if (!file) {
    return NextResponse.json({ error: "No CSV file found in logs/" }, { status: 404 });
  }

  const stat = statSync(file);
  const rows = parseCsv(readFileSync(file, "utf8"));
  if (rows.length === 0) {
    return NextResponse.json({
      error: "CSV exists but has no data rows yet",
      file: { name: path.basename(file), rows: 0 },
    }, { status: 200 });
  }

  // ── Build numeric columns once ──────────────────────────────
  const tradesCum     = rows.map((r) => n(r.trades_received));
  const parse_ns      = rows.map((r) => n(r.avg_parse_ns));
  const process_ns    = rows.map((r) => n(r.avg_process_ns));
  const cpu_pct       = rows.map((r) => n(r.cpu_pct));
  const sip_latency   = rows.map((r) => n(r.sip_latency_ms));
  const exch_latency  = rows.map((r) => n(r.exchange_latency_ms));
  const ring_depth    = rows.map((r) => n(r.ring_depth));
  const ring_capacity = n(rows[0].ring_capacity) || 1;
  const ring_dropped  = rows.map((r) => n(r.ring_dropped));
  const recvq         = rows.map((r) => n(r.kernel_recvq_bytes));
  const recvbuf       = n(rows[0].kernel_recvbuf_bytes) || 1;
  const rcv_wnd       = rows.map((r) => n(r.tcp_rcv_wnd_bytes));
  const ws_pushed     = rows.map((r) => n(r.ws_messages_pushed));
  // Phase 2 — quotes_received is cumulative. Old CSVs without this
  // column will get 0 from `n(undefined)`.
  const quotesCum     = rows.map((r) => n(r.quotes_received));

  // ── Peaks-since-last-tick columns (added 2026-05-01) ────────
  // These are the columns Polygon's "Buffer ↑" correlates with.
  // They may not exist in OLD CSV files written before the peak-
  // tracking change — fall back to 0 in that case so the route
  // still serves legacy logs without crashing.
  const ring_depth_max  = rows.map((r) => n(r.ring_depth_max));
  const recvq_max       = rows.map((r) => n(r.recvq_max_bytes));
  const rcv_wnd_min     = rows.map((r) => n(r.rcv_wnd_min_bytes));
  const rcv_wnd_zero    = rows.map((r) => n(r.rcv_wnd_zero_count));
  const drops_delta     = rows.map((r) => n(r.ring_dropped_delta));

  // ── Per-tick deltas (needed for trades-per-sec chart) ───────
  const TICK_SEC = 5;
  const series = rows.map((r, i) => {
    const tradesDelta = i === 0 ? tradesCum[0] : tradesCum[i] - tradesCum[i - 1];
    return {
      iso:                r.timestamp_iso,
      t_sec:              i * TICK_SEC,
      trades_per_tick:    Math.max(0, tradesDelta),
      trades_per_sec:     Math.max(0, tradesDelta) / TICK_SEC,
      parse_ns:           parse_ns[i],
      process_ns:         process_ns[i],
      cpu_pct:            cpu_pct[i],
      sip_latency_ms:     sip_latency[i],
      ring_depth:         ring_depth[i],
      ring_depth_max:     ring_depth_max[i],
      ring_pct:           (ring_depth[i] / ring_capacity) * 100,
      ring_pct_max:       (ring_depth_max[i] / ring_capacity) * 100,
      recvq_bytes:        recvq[i],
      recvq_max_bytes:    recvq_max[i],
      rcv_wnd_bytes:      rcv_wnd[i],
      rcv_wnd_min_bytes:  rcv_wnd_min[i],
      rcv_wnd_zero_count: rcv_wnd_zero[i],
      ring_dropped_delta: drops_delta[i],
      last_symbol:        r.last_symbol,
      last_price:         n(r.last_price),
      last_size:          n(r.last_size),
    };
  });

  // ── Aggregates ──────────────────────────────────────────────
  const sortedSip       = [...sip_latency].sort((a, b) => a - b);
  const sortedParse     = [...parse_ns].sort((a, b) => a - b);
  const sortedProcess   = [...process_ns].sort((a, b) => a - b);

  const tradesTotal     = tradesCum[tradesCum.length - 1] - tradesCum[0];
  const dropsTotal      = ring_dropped[ring_dropped.length - 1];
  const wsPushedTotal   = ws_pushed[ws_pushed.length - 1] - ws_pushed[0];
  // Phase 2 — total quotes ingested over the run. Per-sec avg is
  // computed below once `durationSec` is available.
  const quotesTotal     = quotesCum.length
    ? quotesCum[quotesCum.length - 1] - quotesCum[0]
    : 0;

  // Peaks now combine snapshot reads with the per-tick peak columns.
  // The peak-since-last-tick columns are the load-bearing ones —
  // they capture sub-5-s bursts the snapshot reads silently miss.
  const ringDepthPeakMax  = Math.max(maxOf(ring_depth), maxOf(ring_depth_max));
  const recvqPeakMax      = Math.max(maxOf(recvq), maxOf(recvq_max));
  const rcvWndAbsMin      = Math.min(
    rcv_wnd.length ? minOf(rcv_wnd) : Infinity,
    rcv_wnd_min.filter((v) => v > 0).length
      ? minOf(rcv_wnd_min.filter((v) => v > 0))
      : Infinity,
  );

  const maxRingPct      = (ringDepthPeakMax / ring_capacity) * 100;
  const maxRecvqPct     = (recvqPeakMax / recvbuf) * 100;
  const dropsDeltaTotal = drops_delta.reduce((s, x) => s + x, 0);
  const wndZeroSeconds  = rcv_wnd_zero.reduce((s, x) => s + x, 0);

  // Backpressure: fire if EITHER the snapshot ever read 0 OR the
  // 1 Hz peak monitor ever caught wnd==0 between samples (much more
  // sensitive). Same idea for drops.
  const bpEvents        = rcv_wnd.filter((v) => v === 0).length + wndZeroSeconds;
  const dropsAny        = dropsTotal > 0 || dropsDeltaTotal > 0;

  const durationSec     = (rows.length - 1) * TICK_SEC;
  const tradesPerSecAvg = durationSec > 0 ? tradesTotal / durationSec : 0;
  const quotesPerSecAvg = durationSec > 0 ? quotesTotal / durationSec : 0;
  const peakTradesSec   = maxOf(series.map((s) => s.trades_per_sec));

  const status = {
    latency: classifyLatency(avg(sip_latency)),
    ring:    classifyRing(maxRingPct),
    cpu:     classifyCpu(maxOf(cpu_pct)),
    drops:   classifyBool(dropsAny),
    backpressure: classifyBool(bpEvents > 0),
  };

  // Last row is freshest snapshot — handy for the "last seen" line.
  const last = rows[rows.length - 1];

  return NextResponse.json({
    file: {
      name:           path.basename(file),
      rows:           rows.length,
      mtime_iso:      stat.mtime.toISOString(),
      start_iso:      rows[0].timestamp_iso,
      end_iso:        last.timestamp_iso,
      duration_sec:   durationSec,
    },
    totals: {
      trades:           tradesTotal,
      // Phase 2 (2026-05-06) — cumulative Q.* count for the run.
      // Old CSVs (pre-quotes_received column) report 0.
      quotes:           quotesTotal,
      ring_dropped:     dropsTotal,
      ring_dropped_delta_sum: dropsDeltaTotal,
      ws_messages:      wsPushedTotal,
      backpressure_events:    bpEvents,
      // 1-Hz samples where rcv_wnd==0 — the literal "STOP" we sent
      // to Polygon (their `Buffer ↑` correlates with this).
      rcv_wnd_zero_seconds:   wndZeroSeconds,
    },
    averages: {
      parse_ns:         Math.round(avg(parse_ns)),
      process_ns:       Math.round(avg(process_ns)),
      cpu_pct:          Number(avg(cpu_pct).toFixed(3)),
      sip_latency_ms:   Math.round(avg(sip_latency)),
      exchange_latency_ms: Math.round(avg(exch_latency)),
      trades_per_sec:   Number(tradesPerSecAvg.toFixed(2)),
      quotes_per_sec:   Number(quotesPerSecAvg.toFixed(2)),
    },
    peaks: {
      parse_ns_p99:     percentile(sortedParse, 99),
      process_ns_p99:   percentile(sortedProcess, 99),
      sip_latency_p99:  percentile(sortedSip, 99),
      sip_latency_max:  maxOf(sip_latency),
      cpu_pct_max:      maxOf(cpu_pct),
      // Ring + recvQ + rcv_wnd peaks now combine snapshot + per-tick
      // peak columns — these catch the bursts that "0" snapshots
      // were hiding. ring_pct_max especially: an instantaneous read
      // of 0 / 2048 was misleading; the real peak across the run
      // can show 800 / 2048 = 39 % during a brief load spike.
      ring_depth_max:   ringDepthPeakMax,
      ring_pct_max:     Number(maxRingPct.toFixed(1)),
      recvq_bytes_max:  recvqPeakMax,
      recvq_pct_max:    Number(maxRecvqPct.toFixed(1)),
      rcv_wnd_min:      Number.isFinite(rcvWndAbsMin) ? rcvWndAbsMin : 0,
      trades_per_sec_peak: Number(peakTradesSec.toFixed(2)),
    },
    constants: {
      ring_capacity:    ring_capacity,
      kernel_recvbuf:   recvbuf,
      tick_seconds:     TICK_SEC,
    },
    last_sample: {
      iso:        last.timestamp_iso,
      symbol:     last.last_symbol,
      price:      n(last.last_price),
      size:       n(last.last_size),
    },
    status,
    series,
  });
}
