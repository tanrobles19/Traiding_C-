"use client";

import { useMemo, useState, useEffect } from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import {
  AreaChart, Area,
  XAxis, YAxis, Tooltip, CartesianGrid, ResponsiveContainer, Brush,
  ReferenceLine,
} from "recharts";
import {
  ArrowLeft, BarChart3, Loader2, Activity, Clock,
} from "lucide-react";
import { useTheme } from "@/components/ThemeProvider";

type SpreadPoint = {
  t: number;
  spread: number;
  bid: number | null;
  ask: number | null;
  bid_sz: number;
  ask_sz: number;
};

type SeriesResponse = {
  symbol: string;
  points: SpreadPoint[];
  stats: {
    count: number;
    first_t?: number;
    last_t?: number;
    min_spread?: number;
    max_spread?: number;
    avg_spread?: number;
    truncated?: boolean;
  } | null;
};

type SymbolsResponse = {
  symbols: { symbol: string; count: number; latest_id: number }[];
};

// Y-axis ticks fixed at the operator-requested scale.
// Negative half is included symmetrically so crossed-market events
// (bid > ask) stay visible instead of getting clipped.
const Y_TICKS = [
  -0.10, -0.05, 0,
  0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 0.40, 0.50, 0.60, 0.70, 0.80, 0.90, 1.00,
];

function formatSpread(v: number): string {
  if (!Number.isFinite(v)) return "";
  const sign = v < 0 ? "-" : "";
  return `${sign}$${Math.abs(v).toFixed(4)}`;
}

function formatTimeMs(ms: number): string {
  const d = new Date(ms);
  const hh = String(d.getHours()).padStart(2, "0");
  const mm = String(d.getMinutes()).padStart(2, "0");
  const ss = String(d.getSeconds()).padStart(2, "0");
  const ms3 = String(d.getMilliseconds()).padStart(3, "0");
  return `${hh}:${mm}:${ss}.${ms3}`;
}

function Tile({
  icon: Icon,
  label,
  value,
  subtitle,
  delayMs,
}: {
  icon: React.ComponentType<{ className?: string }>;
  label: string;
  value: string;
  subtitle?: string;
  delayMs: number;
}) {
  return (
    <div
      className="rounded-2xl bg-zinc-900/[0.03] dark:bg-white/[0.03] border border-zinc-900/5 dark:border-white/5 px-5 py-4 shadow-lg shadow-black/5 dark:shadow-black/20"
      style={{ animation: "fadeSlideUp 0.6s ease-out both", animationDelay: `${delayMs}ms` }}
    >
      <div className="flex items-center gap-2 text-[10px] uppercase tracking-[0.22em] text-zinc-500">
        <Icon className="size-3.5" />
        {label}
      </div>
      <div className="mt-2 font-mono tabular-nums text-2xl font-bold text-zinc-900 dark:text-white">
        {value}
      </div>
      {subtitle && (
        <div className="mt-1 text-[11px] text-zinc-500 dark:text-zinc-400">
          {subtitle}
        </div>
      )}
    </div>
  );
}

export default function SpreadChartPage() {
  const { theme } = useTheme();
  const isDark = theme === "dark";

  const gridColor    = isDark ? "rgba(255,255,255,0.06)" : "rgba(0,0,0,0.06)";
  const axisColor    = isDark ? "rgba(255,255,255,0.15)" : "rgba(0,0,0,0.15)";
  const axisTextFill = isDark ? "#a1a1aa" : "#52525b";
  const tooltipBg    = isDark ? "#18181b" : "#ffffff";
  const tooltipText  = isDark ? "#fafafa" : "#18181b";
  const tooltipBdr   = isDark ? "rgba(255,255,255,0.1)" : "rgba(0,0,0,0.08)";

  const [symbol, setSymbol] = useState<string>("");

  // Sync `?symbol=…` ↔ state so this page is shareable.
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const s = params.get("symbol");
    if (s) setSymbol(s.toUpperCase());
  }, []);
  useEffect(() => {
    if (!symbol) return;
    const params = new URLSearchParams(window.location.search);
    if (params.get("symbol") === symbol) return;
    params.set("symbol", symbol);
    window.history.replaceState({}, "", `?${params.toString()}`);
  }, [symbol]);

  const symbolsQuery = useQuery<SymbolsResponse>({
    queryKey: ["raw-quotes-symbols"],
    queryFn: async () => {
      const r = await fetch("/api/raw-quotes/symbols");
      if (!r.ok) throw new Error("symbols fetch failed");
      return r.json();
    },
    refetchInterval: 5_000,
  });

  // Pick the most-recent symbol by default.
  useEffect(() => {
    if (!symbol && symbolsQuery.data?.symbols?.[0]?.symbol) {
      setSymbol(symbolsQuery.data.symbols[0].symbol);
    }
  }, [symbol, symbolsQuery.data]);

  const seriesQuery = useQuery<SeriesResponse>({
    queryKey: ["raw-quotes-series", symbol],
    queryFn: async () => {
      const r = await fetch(`/api/raw-quotes/series?symbol=${encodeURIComponent(symbol)}`);
      if (!r.ok) throw new Error("series fetch failed");
      return r.json();
    },
    enabled: !!symbol,
    refetchInterval: 5_000,
  });

  const data = seriesQuery.data?.points ?? [];
  const stats = seriesQuery.data?.stats ?? null;

  const xDomain = useMemo<[number, number]>(() => {
    if (!stats || stats.first_t == null || stats.last_t == null) return [0, 1];
    return [stats.first_t, stats.last_t];
  }, [stats]);

  const xTicks = useMemo<number[]>(() => {
    if (!stats || stats.first_t == null || stats.last_t == null) return [];
    const span = stats.last_t - stats.first_t;
    if (span <= 0) return [stats.first_t];
    const N = 8;
    const out: number[] = [];
    for (let i = 0; i < N; i++) {
      out.push(stats.first_t + (span * i) / (N - 1));
    }
    return out;
  }, [stats]);

  return (
    <div className="flex flex-col h-full px-6 py-6 gap-5 overflow-y-auto max-w-[120rem] mx-auto w-full">
      {/* ── header ─────────────────────────────────────────────── */}
      <div
        className="flex items-end justify-between flex-wrap gap-4"
        style={{ animation: "fadeSlideUp 0.6s ease-out both" }}
      >
        <div>
          <Link
            href="/raw-trades"
            className="inline-flex items-center gap-1.5 text-[11px] uppercase tracking-[0.22em] text-zinc-500 hover:text-amber-600 dark:hover:text-amber-400 transition-colors"
          >
            <ArrowLeft className="size-3" /> Raw Tape
          </Link>
          <h1 className="mt-2 text-3xl font-bold tracking-tight text-zinc-900 dark:text-white">
            Spread chart {symbol && <span className="text-amber-600 dark:text-amber-400">· {symbol}</span>}
          </h1>
          <div className="mt-3 h-0.5 w-16 rounded-full bg-gradient-to-r from-amber-400 to-orange-500" />
        </div>

        {/* symbol selector */}
        <div className="flex items-center gap-3">
          <label className="text-[10px] uppercase tracking-[0.2em] text-zinc-500">
            Symbol
          </label>
          <select
            value={symbol}
            onChange={(e) => setSymbol(e.target.value)}
            disabled={!symbolsQuery.data}
            className="h-9 px-3 rounded-xl border border-zinc-900/10 dark:border-white/10 bg-white/60 dark:bg-white/[0.03] text-sm font-mono tabular-nums text-zinc-900 dark:text-zinc-100 outline-none focus:border-amber-500/50 focus:ring-2 focus:ring-amber-500/20 cursor-pointer"
          >
            {symbolsQuery.data?.symbols?.map((s) => (
              <option key={s.symbol} value={s.symbol}>
                {s.symbol} · {s.count.toLocaleString()} quotes
              </option>
            ))}
          </select>
        </div>
      </div>

      {/* ── KPI tiles ──────────────────────────────────────────── */}
      {stats && stats.count > 0 && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <Tile
            icon={Activity}
            label="Avg spread"
            value={formatSpread(stats.avg_spread ?? 0)}
            subtitle={
              (stats.avg_spread ?? 0) > 0.10
                ? "Wide regime — MMs uncertain"
                : "Healthy market"
            }
            delayMs={80}
          />
          <Tile
            icon={Activity}
            label="Worst spread (max)"
            value={formatSpread(stats.max_spread ?? 0)}
            subtitle="Peak MM defensive position"
            delayMs={160}
          />
          <Tile
            icon={Activity}
            label="Best spread (min)"
            value={formatSpread(stats.min_spread ?? 0)}
            subtitle={
              (stats.min_spread ?? 0) < 0
                ? "Crossed market detected"
                : "Tightest market state"
            }
            delayMs={240}
          />
          <Tile
            icon={Clock}
            label="Quotes"
            value={stats.count.toLocaleString()}
            subtitle={
              stats.first_t != null && stats.last_t != null
                ? `${formatTimeMs(stats.first_t)} → ${formatTimeMs(stats.last_t)}`
                : ""
            }
            delayMs={320}
          />
        </div>
      )}

      {/* ── spread chart ───────────────────────────────────────── */}
      <div
        className="rounded-2xl bg-zinc-900/[0.03] dark:bg-white/[0.03] border border-zinc-900/5 dark:border-white/5 p-5 shadow-lg shadow-black/5 dark:shadow-black/20 flex flex-col"
        style={{ animation: "fadeSlideUp 0.6s ease-out both", animationDelay: "200ms", height: 600 }}
      >
        <div className="flex items-center gap-3 mb-2">
          <div className="size-8 rounded-xl bg-amber-500/10 border border-amber-500/20 flex items-center justify-center">
            <BarChart3 className="size-4 text-amber-600 dark:text-amber-400" />
          </div>
          <div className="text-[10px] uppercase tracking-[0.2em] text-zinc-500">
            Spread (ask − bid) · {symbol || "—"}
          </div>
        </div>

        <div className="flex-1 mt-2 min-h-0">
          {seriesQuery.isFetching && data.length === 0 && (
            <div className="h-full flex items-center justify-center text-sm text-zinc-500 dark:text-zinc-400">
              <Loader2 className="size-4 animate-spin mr-2" />
              Loading…
            </div>
          )}
          {data.length === 0 && !seriesQuery.isFetching ? (
            <div className="h-full flex items-center justify-center text-sm text-zinc-500 dark:text-zinc-400">
              No quotes for {symbol || "—"}
            </div>
          ) : (
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={data} margin={{ top: 5, right: 12, left: 4, bottom: 0 }}>
                <defs>
                  <linearGradient id="spreadArea" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%"  stopColor="#fbbf24" stopOpacity={0.45} />
                    <stop offset="100%" stopColor="#f97316" stopOpacity={0.02} />
                  </linearGradient>
                </defs>
                <CartesianGrid stroke={gridColor} strokeDasharray="2 4" vertical={false} />
                <XAxis
                  dataKey="t"
                  type="number"
                  scale="time"
                  domain={xDomain}
                  ticks={xTicks}
                  tickFormatter={formatTimeMs}
                  tick={{ fill: axisTextFill, fontSize: 10 }}
                  stroke={axisColor}
                  minTickGap={50}
                />
                <YAxis
                  domain={[-0.10, 1.00]}
                  ticks={Y_TICKS}
                  tickFormatter={formatSpread}
                  tick={{ fill: axisTextFill, fontSize: 10 }}
                  stroke={axisColor}
                  width={78}
                />
                {/* Reference lines for the operator-meaningful zones */}
                <ReferenceLine y={0}    stroke="#71717a" strokeDasharray="4 4" />
                <ReferenceLine y={0.10} stroke="#a16207" strokeDasharray="2 4" />
                <ReferenceLine y={0.50} stroke="#dc2626" strokeDasharray="2 4" />
                <Tooltip
                  cursor={{ stroke: "#f59e0b", strokeWidth: 1, strokeDasharray: "3 3" }}
                  contentStyle={{
                    background: tooltipBg,
                    border: `1px solid ${tooltipBdr}`,
                    borderRadius: 12,
                    fontSize: 12,
                    color: tooltipText,
                    boxShadow: "0 10px 40px rgba(0,0,0,0.2)",
                  }}
                  labelFormatter={(v) => formatTimeMs(Number(v))}
                  formatter={((v: unknown) => {
                    const n = Number(v);
                    if (!Number.isFinite(n)) return ["", "Spread"];
                    return [formatSpread(n), "Spread"];
                  // eslint-disable-next-line @typescript-eslint/no-explicit-any
                  }) as any}
                />
                <Area
                  type="stepAfter"
                  dataKey="spread"
                  stroke="#f59e0b"
                  strokeWidth={1}
                  fill="url(#spreadArea)"
                  isAnimationActive={false}
                  dot={false}
                  activeDot={{ r: 3, fill: "#f59e0b", stroke: "#fff" }}
                />
                <Brush
                  dataKey="t"
                  height={20}
                  stroke="#f59e0b"
                  fill="rgba(251,191,36,0.08)"
                  travellerWidth={8}
                  tickFormatter={formatTimeMs}
                />
              </AreaChart>
            </ResponsiveContainer>
          )}
        </div>
      </div>

      {stats?.truncated && (
        <div className="text-[11px] text-amber-600 dark:text-amber-400">
          Showing the first 10,000 quotes. Filter by minute or download a smaller window for tighter zoom.
        </div>
      )}
    </div>
  );
}
