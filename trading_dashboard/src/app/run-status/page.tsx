"use client";

// System Status — telemetry of the most recent C++ trader run.
//
// Auto-loads the newest CSV from cpp_ultra_low_latency/logs/, polls
// every 5 s (same cadence as the rest of the dashboard). All shaping
// happens server-side in /api/run-status; this file is pure render.

import { useQuery } from "@tanstack/react-query";
import {
  Activity, Cpu, Gauge, Network, Wifi,
  TrendingUp, FileText, Zap, AlertTriangle, CheckCircle2,
  Timer, Flame,
} from "lucide-react";
import {
  AreaChart, Area, LineChart, Line, BarChart, Bar,
  XAxis, YAxis, Tooltip, CartesianGrid, ResponsiveContainer,
} from "recharts";

type Health = "green" | "yellow" | "red";

type SignalLatency = {
  count: number;
  stats?: {
    avg_ms: number;
    p50_ms: number;
    p95_ms: number;
    p99_ms: number;
    min_ms: number;
    max_ms: number;
  };
  peak?: { symbol: string; latency_ms: number; iso: string };
  top_peaks?: { symbol: string; latency_ms: number; iso: string }[];
  series?: { iso: string; symbol: string; latency_ms: number }[];
  message?: string;
};

type RunStatus = {
  file: {
    name: string;
    rows: number;
    mtime_iso: string;
    start_iso: string;
    end_iso: string;
    duration_sec: number;
  };
  totals: {
    trades: number;
    quotes: number;
    ring_dropped: number;
    ring_dropped_delta_sum: number;
    ws_messages: number;
    backpressure_events: number;
    rcv_wnd_zero_seconds: number;
  };
  averages: {
    parse_ns: number;
    process_ns: number;
    cpu_pct: number;
    sip_latency_ms: number;
    exchange_latency_ms: number;
    trades_per_sec: number;
    quotes_per_sec: number;
  };
  peaks: {
    parse_ns_p99: number;
    process_ns_p99: number;
    sip_latency_p99: number;
    sip_latency_max: number;
    cpu_pct_max: number;
    ring_depth_max: number;
    ring_pct_max: number;
    recvq_bytes_max: number;
    recvq_pct_max: number;
    rcv_wnd_min: number;
    trades_per_sec_peak: number;
  };
  constants: {
    ring_capacity: number;
    kernel_recvbuf: number;
    tick_seconds: number;
  };
  last_sample: {
    iso: string;
    symbol: string;
    price: number;
    size: number;
  };
  status: {
    latency: Health;
    ring: Health;
    cpu: Health;
    drops: Health;
    backpressure: Health;
  };
  series: {
    iso: string;
    t_sec: number;
    trades_per_tick: number;
    trades_per_sec: number;
    parse_ns: number;
    process_ns: number;
    cpu_pct: number;
    sip_latency_ms: number;
    ring_depth: number;
    ring_depth_max: number;
    ring_pct: number;
    ring_pct_max: number;
    recvq_bytes: number;
    recvq_max_bytes: number;
    rcv_wnd_bytes: number;
    rcv_wnd_min_bytes: number;
    rcv_wnd_zero_count: number;
    ring_dropped_delta: number;
    last_symbol: string;
    last_price: number;
    last_size: number;
  }[];
};

const HEALTH_STYLES: Record<Health, { bg: string; text: string; ring: string; label: string }> = {
  green:  { bg: "bg-emerald-500/10", text: "text-emerald-700 dark:text-emerald-400",
            ring: "border-emerald-500/30", label: "Healthy"   },
  yellow: { bg: "bg-amber-500/10",   text: "text-amber-700   dark:text-amber-400",
            ring: "border-amber-500/30",   label: "Degraded"  },
  red:    { bg: "bg-rose-500/10",    text: "text-rose-700    dark:text-rose-400",
            ring: "border-rose-500/30",    label: "Critical"  },
};

function fmt(n: number): string {
  return n.toLocaleString("en-US");
}
function fmtBytes(n: number): string {
  if (n >= 1024 * 1024) return (n / (1024 * 1024)).toFixed(1) + " MB";
  if (n >= 1024)        return (n / 1024).toFixed(1) + " KB";
  return n + " B";
}
function fmtDuration(sec: number): string {
  const m = Math.floor(sec / 60);
  const s = sec % 60;
  if (m === 0) return `${s}s`;
  return `${m}m ${s}s`;
}

// Format a millisecond value with auto unit:
//   < 1000 ms  → "234 ms"
//   ≥ 1000 ms  → "2.6 s"
//   ≥ 60000 ms → "1m 23s"
function fmtLatency(ms: number): string {
  if (!Number.isFinite(ms)) return "—";
  if (ms < 1000) return `${ms.toLocaleString("en-US")} ms`;
  if (ms < 60_000) return `${(ms / 1000).toFixed(1)} s`;
  const m = Math.floor(ms / 60_000);
  const s = Math.round((ms % 60_000) / 1000);
  return `${m}m ${s}s`;
}
function shortIso(iso: string): string {
  // "2026-05-01T06:46:14.837" → "06:46:14"
  const m = iso.match(/T(\d{2}:\d{2}:\d{2})/);
  return m ? m[1] : iso;
}

function StatusPill({ kind, label, value, hint }: {
  kind: Health; label: string; value: string; hint?: string;
}) {
  const s = HEALTH_STYLES[kind];
  return (
    <div className={[
      "rounded-2xl border p-5 transition-all duration-300 hover:-translate-y-0.5",
      "bg-zinc-900/[0.03] dark:bg-white/[0.03] border-zinc-900/5 dark:border-white/5",
    ].join(" ")}>
      <div className="flex items-center justify-between">
        <div className="text-[10px] font-medium uppercase tracking-[0.22em] text-zinc-500">
          {label}
        </div>
        <span className={[
          "px-2 py-0.5 rounded-full text-[10px] uppercase tracking-wider font-semibold border",
          s.bg, s.text, s.ring,
        ].join(" ")}>
          {s.label}
        </span>
      </div>
      <div className="mt-3 text-2xl font-bold tabular-nums tracking-tight text-zinc-900 dark:text-white">
        {value}
      </div>
      {hint && <div className="mt-1 text-xs text-zinc-500 dark:text-zinc-400">{hint}</div>}
    </div>
  );
}

function StatTile({ label, value, hint, icon: Icon, delayMs, tooltip }: {
  label: string; value: string; hint?: string;
  icon: React.ComponentType<{ className?: string }>; delayMs: number;
  tooltip?: string;
}) {
  return (
    <div
      title={tooltip}
      className="rounded-2xl bg-zinc-900/[0.03] dark:bg-white/[0.03] border border-zinc-900/5 dark:border-white/5 p-5 transition-all duration-500 ease-out hover:-translate-y-1 cursor-help"
      style={{ animation: `fadeSlideUp 0.6s ease-out both`, animationDelay: `${delayMs}ms` }}
    >
      <div className="size-9 rounded-xl bg-amber-500/10 border border-amber-500/20 flex items-center justify-center">
        <Icon className="size-4 text-amber-600 dark:text-amber-400" />
      </div>
      <div className="mt-4 text-[10px] font-medium uppercase tracking-[0.22em] text-zinc-500">
        {label}
      </div>
      <div className="mt-1 text-2xl font-bold tabular-nums tracking-tight text-zinc-900 dark:text-white">
        {value}
      </div>
      {hint && <div className="mt-1 text-xs text-zinc-500 dark:text-zinc-400">{hint}</div>}
    </div>
  );
}

function ChartCard({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="rounded-2xl bg-zinc-900/[0.03] dark:bg-white/[0.03] border border-zinc-900/5 dark:border-white/5 p-5">
      <div className="text-[10px] font-medium uppercase tracking-[0.22em] text-zinc-500 mb-3">
        {title}
      </div>
      <div className="h-[220px] w-full">
        {children}
      </div>
    </div>
  );
}

const AXIS_TICK = { fontSize: 11, fill: "currentColor", opacity: 0.6 };

export default function RunStatusPage() {
  const { data, error, isLoading } = useQuery<RunStatus>({
    queryKey: ["run-status"],
    queryFn: async () => {
      const r = await fetch("/api/run-status");
      if (!r.ok) {
        const j = await r.json().catch(() => ({}));
        throw new Error(j.error || `HTTP ${r.status}`);
      }
      return r.json();
    },
    refetchInterval: 5_000,
  });

  const { data: latency } = useQuery<SignalLatency>({
    queryKey: ["signal-latency"],
    queryFn: async () => {
      const r = await fetch("/api/signal-latency");
      if (!r.ok) {
        const j = await r.json().catch(() => ({}));
        throw new Error(j.error || `HTTP ${r.status}`);
      }
      return r.json();
    },
    refetchInterval: 5_000,
  });

  return (
    <div className="px-8 py-10 max-w-7xl mx-auto">
      <div style={{ animation: "fadeSlideUp 0.6s ease-out both" }}>
        <div className="text-[11px] uppercase tracking-[0.22em] text-zinc-500">
          Run Telemetry
        </div>
        <h1 className="mt-2 text-3xl font-bold tracking-tight text-zinc-900 dark:text-white">
          System status
        </h1>
        <div className="mt-3 h-0.5 w-16 rounded-full bg-gradient-to-r from-amber-400 to-orange-500" />
        {data && (
          <div className="mt-4 text-xs text-zinc-500 dark:text-zinc-400 font-mono flex flex-wrap gap-x-4 gap-y-1">
            <span><FileText className="inline size-3 mr-1" />{data.file.name}</span>
            <span>{data.file.rows} ticks</span>
            <span>{fmtDuration(data.file.duration_sec)} of run</span>
            <span>last: {shortIso(data.last_sample.iso)} {data.last_sample.symbol} ${data.last_sample.price.toFixed(4)}</span>
          </div>
        )}
      </div>

      {isLoading && (
        <div className="mt-10 text-zinc-500 text-sm">Loading run telemetry…</div>
      )}
      {error && (
        <div className="mt-10 rounded-2xl border border-rose-500/30 bg-rose-500/10 p-5 text-rose-700 dark:text-rose-400">
          <div className="flex items-center gap-2">
            <AlertTriangle className="size-4" />
            <span className="font-semibold">Could not load telemetry</span>
          </div>
          <div className="mt-1 text-sm font-mono">{(error as Error).message}</div>
        </div>
      )}

      {data && (
        <>
          {/* ── HEALTH PANEL ──────────────────────────────────────── */}
          <div className="mt-10">
            <div className="text-[11px] uppercase tracking-[0.22em] text-zinc-500 mb-3">
              Health indicators
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-4">
              <StatusPill
                kind={data.status.latency}
                label="Upstream latency"
                value={`${fmt(data.averages.sip_latency_ms)} ms`}
                hint={`p99 ${fmt(data.peaks.sip_latency_p99)} ms · max ${fmt(data.peaks.sip_latency_max)} ms`}
              />
              <StatusPill
                kind={data.status.ring}
                label="Ring buffer"
                value={`${data.peaks.ring_pct_max.toFixed(1)} %`}
                hint={`peak depth ${fmt(data.peaks.ring_depth_max)} / ${fmt(data.constants.ring_capacity)}`}
              />
              <StatusPill
                kind={data.status.cpu}
                label="CPU utilisation"
                value={`${data.peaks.cpu_pct_max.toFixed(2)} %`}
                hint={`avg ${data.averages.cpu_pct.toFixed(3)} % across run`}
              />
              <StatusPill
                kind={data.status.drops}
                label="Ring drops"
                value={fmt(data.totals.ring_dropped + data.totals.ring_dropped_delta_sum)}
                hint={data.totals.ring_dropped === 0 && data.totals.ring_dropped_delta_sum === 0
                  ? "none — processor kept up"
                  : "data lost — processor fell behind"}
              />
              <StatusPill
                kind={data.status.backpressure}
                label="Backpressure"
                value={fmt(data.totals.rcv_wnd_zero_seconds)}
                hint={data.totals.rcv_wnd_zero_seconds === 0
                  ? `min rcv_wnd ${fmtBytes(data.peaks.rcv_wnd_min)}`
                  : `${data.totals.rcv_wnd_zero_seconds}s with rcv_wnd=0 — STOP sent to Polygon`}
              />
            </div>
          </div>

          {/* ── KEY METRICS ────────────────────────────────────────── */}
          <div className="mt-10">
            <div className="text-[11px] uppercase tracking-[0.22em] text-zinc-500 mb-3">
              Key metrics
            </div>
            <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4">
              <StatTile
                label="Total trades"
                value={fmt(data.totals.trades)}
                hint={`${data.averages.trades_per_sec.toFixed(1)}/s avg`}
                icon={TrendingUp} delayMs={40}
                tooltip="Cumulative count of trade executions consumed from the Polygon WebSocket since the C++ trader started. Excludes quotes (those are top-of-book updates, not executions). The hint below shows the lifetime average ingestion rate. Useful as the denominator for rate-based diagnostics."
              />
              <StatTile
                label="Peak rate"
                value={`${fmt(Math.round(data.peaks.trades_per_sec_peak))}/s`}
                hint="single 5 s tick"
                icon={Zap} delayMs={80}
                tooltip="Highest single 5-second window of trade ingestion observed in this run. Measures the worst-case load the processor had to handle, NOT the average. Compare against your headroom budget — if this approaches the per-trade-cost ceiling, the system is one event away from falling behind."
              />
              <StatTile
                label="Parse"
                value={`${fmt(data.averages.parse_ns)} ns`}
                hint={`p99 ${fmt(data.peaks.parse_ns_p99)} ns`}
                icon={Cpu} delayMs={120}
                tooltip="Mean time the single-pass byte scanner spends turning one Polygon WebSocket message into a Trade struct, in nanoseconds. The p99 is the 99th-percentile worst case across the run — your tail latency. Anything below ~1µs is healthy; sustained > 10µs would suggest the parser is being asked to handle malformed or oversized JSON."
              />
              <StatTile
                label="Process"
                value={`${fmt(data.averages.process_ns)} ns`}
                hint={`p99 ${fmt(data.peaks.process_ns_p99)} ns`}
                icon={Cpu} delayMs={160}
                tooltip="Mean per-trade cost of the full strategy pipeline: condition gates, OHLCV update, RV check, dedup, prediction, and signal/order push. The p99 is the worst case. Process + Parse together set the trades-per-second ceiling: 1e9 / (parse_ns + process_ns) ≈ theoretical max trades the single processor thread can absorb."
              />
              <StatTile
                label="WS messages"
                value={fmt(data.totals.ws_messages)}
                hint="frames pushed onto ring1"
                icon={Wifi} delayMs={200}
                tooltip="Cumulative number of WebSocket frames pushed from the reader thread onto the lock-free SPSC ring. Each frame can carry several trades and/or quotes batched by Polygon. With Q.* subscription active, this includes both T.<sym> and Q.<sym> events — diverges from Total Trades because quotes do not increment that counter."
              />
              <StatTile
                label="Recv-Q peak"
                value={fmtBytes(data.peaks.recvq_bytes_max)}
                hint={`${data.peaks.recvq_pct_max.toFixed(1)} % of kernel buffer`}
                icon={Network} delayMs={240}
                tooltip="Maximum bytes seen sitting in the kernel TCP receive queue, sampled at 1Hz. If this stays near zero the reader thread is consuming as fast as Polygon delivers — the system is NOT the bottleneck. Climbing toward the kernel buffer cap (8 MB) means the reader fell behind; sustained 100% would force TCP backpressure to Polygon."
              />
            </div>
          </div>

          {/* ── STREAM THROUGHPUT (T.* and Q.* ingestion) ──────────── */}
          <div className="mt-10">
            <div className="text-[11px] uppercase tracking-[0.22em] text-zinc-500 mb-3">
              Stream throughput
            </div>
            <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4">
              <StatTile
                label="Total quotes"
                value={fmt(data.totals.quotes)}
                hint={`${data.averages.quotes_per_sec.toFixed(1)}/s avg`}
                icon={Wifi} delayMs={40}
                tooltip="Cumulative count of NBBO quote updates (Q.* events) consumed from the Polygon WebSocket since the C++ trader started. Each quote represents a change to the best bid or best ask for some symbol. Quotes are an order of magnitude denser than trades; ratio quotes/trades is a microstructure-quality indicator. Old runs without Q.* subscription report 0."
              />
            </div>
          </div>

          {/* ── PEAK DIAGNOSTICS (sub-5s bursts the snapshots miss) ── */}
          <div className="mt-10">
            <div className="text-[11px] uppercase tracking-[0.22em] text-zinc-500 mb-3">
              Peak diagnostics · sub-5s bursts
            </div>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4">
              <StatTile
                label="Ring depth peak"
                value={`${fmt(data.peaks.ring_depth_max)} / ${fmt(data.constants.ring_capacity)}`}
                hint={`${data.peaks.ring_pct_max.toFixed(1)} % — peak between ticks`}
                icon={Gauge} delayMs={40}
              />
              <StatTile
                label="Recv-Q peak"
                value={fmtBytes(data.peaks.recvq_bytes_max)}
                hint={`${data.peaks.recvq_pct_max.toFixed(1)} % of kernel buffer`}
                icon={Network} delayMs={80}
              />
              <StatTile
                label="rcv_wnd min"
                value={fmtBytes(data.peaks.rcv_wnd_min)}
                hint={data.peaks.rcv_wnd_min === 0 ? "hit zero — STOP to Polygon" : "always > 0 — never paused"}
                icon={Wifi} delayMs={120}
              />
              <StatTile
                label="STOP seconds"
                value={`${fmt(data.totals.rcv_wnd_zero_seconds)} s`}
                hint={data.totals.rcv_wnd_zero_seconds === 0
                  ? "no STOP signals to Polygon"
                  : "Polygon's Buffer ↑ should match"}
                icon={AlertTriangle} delayMs={160}
              />
            </div>

            {/* Bottleneck attribution legend */}
            <div className="rounded-2xl border border-zinc-900/5 dark:border-white/5 bg-zinc-900/[0.02] dark:bg-white/[0.02] p-4">
              <div className="text-[10px] font-medium uppercase tracking-[0.22em] text-zinc-500 mb-2">
                Bottleneck attribution
              </div>
              <div className="text-xs text-zinc-600 dark:text-zinc-400 leading-relaxed space-y-1">
                <div><span className="font-mono font-semibold text-zinc-900 dark:text-white">Ring depth peak ↑</span>, recvQ ≈ 0 → <span className="text-amber-700 dark:text-amber-400">processor (CPU) fell behind</span></div>
                <div><span className="font-mono font-semibold text-zinc-900 dark:text-white">Recv-Q peak ↑</span>, rcv_wnd → 0, STOP seconds &gt; 0 → <span className="text-amber-700 dark:text-amber-400">network / reader path was the bottleneck</span></div>
                <div>Both ↑ → combined pressure</div>
                <div>All zero but Polygon reports `Buffer ↑` → <span className="text-rose-700 dark:text-rose-400">instrumentation gap, investigate</span></div>
              </div>
            </div>
          </div>

          {/* ── CHARTS ─────────────────────────────────────────────── */}
          <div className="mt-10">
            <div className="text-[11px] uppercase tracking-[0.22em] text-zinc-500 mb-3">
              Time series
            </div>
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
              <ChartCard title="Trades per second">
                <ResponsiveContainer>
                  <BarChart data={data.series} margin={{ top: 5, right: 10, left: 0, bottom: 0 }}>
                    <defs>
                      <linearGradient id="grTrades" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="0%" stopColor="#fbbf24" />
                        <stop offset="100%" stopColor="#f97316" />
                      </linearGradient>
                    </defs>
                    <CartesianGrid stroke="currentColor" strokeOpacity={0.08} vertical={false} />
                    <XAxis dataKey="iso" tick={AXIS_TICK} tickFormatter={shortIso} interval="preserveStartEnd" />
                    <YAxis tick={AXIS_TICK} />
                    <Tooltip
                      contentStyle={{ background: "rgba(24,24,27,0.95)", border: "1px solid rgba(255,255,255,0.1)", borderRadius: 12, fontSize: 12 }}
                      labelFormatter={(label) => shortIso(String(label))}
                      formatter={(v) => [`${Number(v).toFixed(1)} t/s`, "rate"]}
                    />
                    <Bar dataKey="trades_per_sec" fill="url(#grTrades)" radius={[3, 3, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </ChartCard>

              <ChartCard title="SIP latency">
                <ResponsiveContainer>
                  <LineChart data={data.series} margin={{ top: 5, right: 10, left: 0, bottom: 0 }}>
                    <CartesianGrid stroke="currentColor" strokeOpacity={0.08} vertical={false} />
                    <XAxis dataKey="iso" tick={AXIS_TICK} tickFormatter={(s) => shortIso(String(s))} interval="preserveStartEnd" />
                    <YAxis
                      tick={AXIS_TICK}
                      // Doubling ticks (0→20→40→80→…) on a sqrt scale.
                      // Heavy-tailed data: most signals are sub-second
                      // but the rare peak hits ~10 min. Linear would
                      // squash everything into the bottom 5 %; sqrt
                      // gives the small values room while still showing
                      // the outlier within the chart area.
                      scale="sqrt"
                      domain={[0, 640_000]}
                      ticks={[0, 20_000, 40_000, 80_000, 160_000, 320_000, 640_000]}
                      tickFormatter={(v) => `${Math.round(Number(v) / 1000)}s`}
                      width={48}
                      allowDataOverflow
                    />
                    <Tooltip
                      contentStyle={{ background: "rgba(24,24,27,0.95)", border: "1px solid rgba(255,255,255,0.1)", borderRadius: 12, fontSize: 12 }}
                      labelFormatter={(label) => shortIso(String(label))}
                      formatter={(v) => [fmtLatency(Number(v)), "sip"]}
                    />
                    <Line type="monotone" dataKey="sip_latency_ms" stroke="#f97316" strokeWidth={2} dot={false} />
                  </LineChart>
                </ResponsiveContainer>
              </ChartCard>

              <ChartCard title="Ring buffer · snapshot vs peak (sub-5s)">
                <ResponsiveContainer>
                  <AreaChart data={data.series} margin={{ top: 5, right: 10, left: 0, bottom: 0 }}>
                    <defs>
                      <linearGradient id="grRing" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="0%" stopColor="#fbbf24" stopOpacity={0.45} />
                        <stop offset="100%" stopColor="#f97316" stopOpacity={0.05} />
                      </linearGradient>
                    </defs>
                    <CartesianGrid stroke="currentColor" strokeOpacity={0.08} vertical={false} />
                    <XAxis dataKey="iso" tick={AXIS_TICK} tickFormatter={(s) => shortIso(String(s))} interval="preserveStartEnd" />
                    <YAxis tick={AXIS_TICK} />
                    <Tooltip
                      contentStyle={{ background: "rgba(24,24,27,0.95)", border: "1px solid rgba(255,255,255,0.1)", borderRadius: 12, fontSize: 12 }}
                      labelFormatter={(label) => shortIso(String(label))}
                      formatter={(v, name) => [
                        `${Number(v)} slots`,
                        String(name) === "ring_depth_max" ? "peak (5s)" : "snapshot",
                      ]}
                    />
                    {/* Snapshot at print time — orange fill */}
                    <Area type="monotone" dataKey="ring_depth" stroke="#f97316" strokeWidth={1.5} fill="url(#grRing)" />
                    {/* Peak between ticks — red overlay, catches sub-5s bursts */}
                    <Line type="monotone" dataKey="ring_depth_max" stroke="#dc2626" strokeWidth={2} dot={false} />
                  </AreaChart>
                </ResponsiveContainer>
              </ChartCard>

              <ChartCard title="CPU usage (%)">
                <ResponsiveContainer>
                  <LineChart data={data.series} margin={{ top: 5, right: 10, left: 0, bottom: 0 }}>
                    <CartesianGrid stroke="currentColor" strokeOpacity={0.08} vertical={false} />
                    <XAxis dataKey="iso" tick={AXIS_TICK} tickFormatter={shortIso} interval="preserveStartEnd" />
                    <YAxis tick={AXIS_TICK} />
                    <Tooltip
                      contentStyle={{ background: "rgba(24,24,27,0.95)", border: "1px solid rgba(255,255,255,0.1)", borderRadius: 12, fontSize: 12 }}
                      labelFormatter={(label) => shortIso(String(label))}
                      formatter={(v) => [`${Number(v).toFixed(3)} %`, "cpu"]}
                    />
                    <Line type="monotone" dataKey="cpu_pct" stroke="#fbbf24" strokeWidth={2} dot={false} />
                  </LineChart>
                </ResponsiveContainer>
              </ChartCard>
            </div>
          </div>

          {/* ── SIGNAL LATENCY (from MySQL) ────────────────────────── */}
          {latency && latency.count > 0 && latency.stats && latency.series && latency.top_peaks && (
            <div className="mt-10">
              <div className="text-[11px] uppercase tracking-[0.22em] text-zinc-500 mb-3">
                TradeSignals latency · {latency.count.toLocaleString("en-US")} rows analysed
              </div>

              <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4 mb-5">
                <StatTile
                  label="Avg latency"
                  value={fmtLatency(latency.stats.avg_ms)}
                  hint="across all signals"
                  icon={Timer} delayMs={40}
                />
                <StatTile
                  label="P50 (median)"
                  value={fmtLatency(latency.stats.p50_ms)}
                  hint="half are below this"
                  icon={Timer} delayMs={80}
                />
                <StatTile
                  label="P95"
                  value={fmtLatency(latency.stats.p95_ms)}
                  hint="upper 5 % live above"
                  icon={Timer} delayMs={120}
                />
                <StatTile
                  label="P99"
                  value={fmtLatency(latency.stats.p99_ms)}
                  hint="extreme tail"
                  icon={Flame} delayMs={160}
                />
                <StatTile
                  label="Min"
                  value={fmtLatency(latency.stats.min_ms)}
                  hint="best transport seen"
                  icon={Timer} delayMs={200}
                />
                <StatTile
                  label="Max"
                  value={fmtLatency(latency.stats.max_ms)}
                  hint={latency.peak ? `${latency.peak.symbol} @ ${shortIso(latency.peak.iso)}` : ""}
                  icon={Flame} delayMs={240}
                />
              </div>

              <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
                <div className="lg:col-span-2">
                  <ChartCard title="Latency per signal — time ordered">
                    <ResponsiveContainer>
                      <LineChart data={latency.series} margin={{ top: 5, right: 10, left: 0, bottom: 0 }}>
                        <CartesianGrid stroke="currentColor" strokeOpacity={0.08} vertical={false} />
                        <XAxis dataKey="iso" tick={AXIS_TICK} tickFormatter={(s) => shortIso(String(s))} interval="preserveStartEnd" />
                        <YAxis tick={AXIS_TICK} />
                        <Tooltip
                          contentStyle={{ background: "rgba(24,24,27,0.95)", border: "1px solid rgba(255,255,255,0.1)", borderRadius: 12, fontSize: 12 }}
                          labelFormatter={(label, payload) => {
                            const sym = (payload as unknown as Array<{payload?: {symbol?: string}}>)?.[0]?.payload?.symbol;
                            return sym ? `${shortIso(String(label))} · ${sym}` : shortIso(String(label));
                          }}
                          formatter={(v) => [fmtLatency(Number(v)), "latency"]}
                        />
                        <Line type="monotone" dataKey="latency_ms" stroke="#f97316" strokeWidth={1.5} dot={{ r: 2, fill: "#f97316" }} />
                      </LineChart>
                    </ResponsiveContainer>
                  </ChartCard>
                </div>

                <div className="rounded-2xl bg-zinc-900/[0.03] dark:bg-white/[0.03] border border-zinc-900/5 dark:border-white/5 p-5">
                  <div className="text-[10px] font-medium uppercase tracking-[0.22em] text-zinc-500 mb-3">
                    Top 10 latency peaks
                  </div>
                  <div className="space-y-2">
                    {latency.top_peaks.map((p, i) => (
                      <div
                        key={`${p.iso}-${p.symbol}-${i}`}
                        className="flex items-center justify-between gap-3 px-3 py-2 rounded-xl bg-zinc-900/[0.03] dark:bg-white/[0.03] border border-zinc-900/5 dark:border-white/5"
                      >
                        <div className="flex items-center gap-2 min-w-0">
                          <span className="size-5 shrink-0 rounded-md bg-amber-500/10 border border-amber-500/20 text-[10px] font-semibold flex items-center justify-center text-amber-700 dark:text-amber-400">
                            {i + 1}
                          </span>
                          <span className="font-mono text-sm text-zinc-900 dark:text-white truncate">
                            {p.symbol}
                          </span>
                          <span className="text-[11px] text-zinc-500 dark:text-zinc-400 font-mono truncate">
                            {shortIso(p.iso)}
                          </span>
                        </div>
                        <div className="font-mono tabular-nums text-sm font-semibold text-amber-700 dark:text-amber-400 shrink-0">
                          {fmtLatency(p.latency_ms)}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* ── FOOTNOTE ───────────────────────────────────────────── */}
          <div className="mt-10 rounded-2xl border border-zinc-900/5 dark:border-white/5 bg-zinc-900/[0.02] dark:bg-white/[0.02] p-5">
            <div className="flex items-start gap-3">
              <CheckCircle2 className="size-4 text-amber-600 dark:text-amber-400 mt-0.5" />
              <div className="text-xs text-zinc-600 dark:text-zinc-400 leading-relaxed">
                Source: <span className="font-mono">{data.file.name}</span> — written by
                <span className="font-mono"> summary_logger.h</span> on the C++ trader,
                one row every {data.constants.tick_seconds} seconds. The dashboard polls
                <span className="font-mono"> /api/run-status</span> every 5 s and always
                surfaces the newest CSV in <span className="font-mono">cpp_ultra_low_latency/logs/</span>.
              </div>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
