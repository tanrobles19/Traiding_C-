"use client";

import { useMemo, useState, useEffect } from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import {
  AreaChart, Area,
  XAxis, YAxis, Tooltip, CartesianGrid, ResponsiveContainer, Brush,
} from "recharts";
import {
  ArrowLeft, LineChart as LineChartIcon, BarChart3, Loader2,
  TrendingUp, TrendingDown, Clock, Layers,
} from "lucide-react";
import { useTheme } from "@/components/ThemeProvider";

type SeriesPoint = { t: number; price: number; volume: number };
type SeriesResponse = {
  symbol: string;
  points: SeriesPoint[];
  stats: {
    count: number;
    first_t: number;
    last_t: number;
    min_price: number;
    max_price: number;
    first_price: number;
    last_price: number;
    total_volume: number;
    truncated: boolean;
  } | null;
};

type SymbolsResponse = {
  symbols: { symbol: string; count: number; latest_id: number }[];
};

// HH:MM:SS.mmm in Costa Rica timezone (matches the rest of the dashboard).
function formatTimeMs(ms: number): string {
  const d = new Date(ms);
  return d.toLocaleTimeString("en-US", {
    hour12: false, hour: "2-digit", minute: "2-digit", second: "2-digit",
    timeZone: "America/Costa_Rica",
  }) + "." + String(d.getMilliseconds()).padStart(3, "0");
}

function formatPrice(n: number): string {
  return n.toLocaleString("en-US", { minimumFractionDigits: 4, maximumFractionDigits: 4 });
}

function formatNumber(n: number): string {
  return n.toLocaleString("en-US");
}

function StatCard({
  icon: Icon, label, value, hint, trend,
}: {
  icon: React.ComponentType<{ className?: string }>;
  label: string;
  value: string;
  hint?: string;
  trend?: "up" | "down" | null;
}) {
  const trendColor =
    trend === "up"   ? "text-emerald-500" :
    trend === "down" ? "text-red-500"     :
    "text-amber-600 dark:text-amber-400";
  return (
    <div className="rounded-2xl bg-zinc-900/[0.03] dark:bg-white/[0.03] border border-zinc-900/5 dark:border-white/5 px-5 py-4 shadow-lg shadow-black/5 dark:shadow-black/20">
      <div className="flex items-center gap-2 text-[10px] uppercase tracking-[0.2em] text-zinc-500">
        <Icon className={`size-3.5 ${trendColor}`} />
        <span>{label}</span>
      </div>
      <div className="mt-1.5 text-xl font-mono tabular-nums text-zinc-900 dark:text-white">
        {value}
      </div>
      {hint && <div className="mt-0.5 text-[11px] text-zinc-500 dark:text-zinc-400">{hint}</div>}
    </div>
  );
}

export default function ChartPage() {
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
    window.history.replaceState(null, "", `?${params.toString()}`);
  }, [symbol]);

  const symbolsQuery = useQuery<SymbolsResponse>({
    queryKey: ["raw-trades-symbols"],
    queryFn: async () => {
      const r = await fetch("/api/raw-trades/symbols");
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
    queryKey: ["raw-trades-series", symbol],
    queryFn: async () => {
      const r = await fetch(`/api/raw-trades/series?symbol=${encodeURIComponent(symbol)}`);
      if (!r.ok) throw new Error("series fetch failed");
      return r.json();
    },
    enabled: !!symbol,
  });

  const { theme } = useTheme();
  const isDark = theme === "dark";
  const gridColor    = isDark ? "rgba(255,255,255,0.05)" : "rgba(0,0,0,0.06)";
  const axisColor    = isDark ? "rgba(255,255,255,0.1)"  : "rgba(0,0,0,0.1)";
  const axisTextFill = isDark ? "#a1a1aa" : "#52525b";
  const tooltipBg    = isDark ? "#18181b" : "#ffffff";
  const tooltipText  = isDark ? "#fafafa" : "#18181b";
  const tooltipBdr   = isDark ? "rgba(255,255,255,0.1)" : "rgba(0,0,0,0.08)";

  const data = seriesQuery.data?.points ?? [];
  const stats = seriesQuery.data?.stats ?? null;

  const yDomain = useMemo<[number, number]>(() => {
    if (!stats) return [0, 1];
    const pad = (stats.max_price - stats.min_price) * 0.05 || stats.max_price * 0.001;
    return [stats.min_price - pad, stats.max_price + pad];
  }, [stats]);

  const xDomain = useMemo<[number, number]>(() => {
    if (!stats) return [0, 1];
    return [stats.first_t, stats.last_t];
  }, [stats]);

  // Explicit X-axis ticks. Recharts' auto-tick algorithm with
  // `type="number" scale="time"` and 600+ points at sub-millisecond
  // resolution generates duplicate keys (`tick-label-… same-value-twice`)
  // → React console error. Pre-computing 8 evenly spaced ticks
  // sidesteps that and gives a stable, readable axis.
  const xTicks = useMemo<number[]>(() => {
    if (!stats) return [];
    const span = stats.last_t - stats.first_t;
    if (span <= 0) return [stats.first_t];
    const N = 8;
    const out: number[] = [];
    for (let i = 0; i < N; i++) {
      out.push(stats.first_t + (span * i) / (N - 1));
    }
    return out;
  }, [stats]);

  const trend: "up" | "down" | null = stats
    ? stats.last_price > stats.first_price ? "up"
    : stats.last_price < stats.first_price ? "down"
    : null
    : null;

  const pctChange = stats && stats.first_price !== 0
    ? ((stats.last_price - stats.first_price) / stats.first_price) * 100
    : 0;

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
            <ArrowLeft className="size-3" /> Raw Trades
          </Link>
          <h1 className="mt-2 text-3xl font-bold tracking-tight text-zinc-900 dark:text-white">
            Price chart {symbol && <span className="text-amber-600 dark:text-amber-400">· {symbol}</span>}
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
            {!symbolsQuery.data && <option>Loading…</option>}
            {symbolsQuery.data?.symbols.length === 0 && <option value="">— no data —</option>}
            {symbolsQuery.data?.symbols.map((s) => (
              <option key={s.symbol} value={s.symbol}>
                {s.symbol} · {s.count.toLocaleString()} ticks
              </option>
            ))}
          </select>
        </div>
      </div>

      {/* ── stats row ──────────────────────────────────────────── */}
      {stats && (
        <div
          className="grid grid-cols-2 md:grid-cols-4 gap-3"
          style={{ animation: "fadeSlideUp 0.6s ease-out both", animationDelay: "100ms" }}
        >
          <StatCard
            icon={trend === "down" ? TrendingDown : TrendingUp}
            label="Last / Open"
            value={`$${formatPrice(stats.last_price)}`}
            hint={`${pctChange >= 0 ? "+" : ""}${pctChange.toFixed(2)}% from open ($${formatPrice(stats.first_price)})`}
            trend={trend}
          />
          <StatCard
            icon={TrendingUp}
            label="High / Low"
            value={`$${formatPrice(stats.max_price)} / $${formatPrice(stats.min_price)}`}
            hint={`Range $${formatPrice(stats.max_price - stats.min_price)}`}
          />
          <StatCard
            icon={Layers}
            label="Total Volume"
            value={formatNumber(stats.total_volume)}
            hint={`${formatNumber(stats.count)} ticks`}
          />
          <StatCard
            icon={Clock}
            label="Time Window"
            value={formatTimeMs(stats.first_t)}
            hint={`→ ${formatTimeMs(stats.last_t)}`}
          />
        </div>
      )}

      {/* ── price chart ────────────────────────────────────────── */}
      <div
        className="rounded-2xl bg-zinc-900/[0.03] dark:bg-white/[0.03] border border-zinc-900/5 dark:border-white/5 p-5 shadow-lg shadow-black/5 dark:shadow-black/20 flex flex-col"
        style={{ animation: "fadeSlideUp 0.6s ease-out both", animationDelay: "200ms", height: 420 }}
      >
        <div className="flex items-center gap-3 mb-2">
          <div className="size-8 rounded-xl bg-amber-500/10 border border-amber-500/20 flex items-center justify-center">
            <LineChartIcon className="size-4 text-amber-600 dark:text-amber-400" />
          </div>
          <div className="text-[10px] uppercase tracking-[0.2em] text-zinc-500">
            Tick price · {symbol || "—"}
          </div>
          {seriesQuery.isFetching && (
            <Loader2 className="size-3.5 animate-spin text-amber-500 ml-2" />
          )}
        </div>

        <div className="flex-1 mt-2 min-h-0">
          {data.length === 0 && !seriesQuery.isFetching ? (
            <div className="h-full flex items-center justify-center text-sm text-zinc-500 dark:text-zinc-400">
              No tick data for this symbol. Download trades on the previous page.
            </div>
          ) : (
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={data} margin={{ top: 10, right: 12, left: 4, bottom: 0 }}>
                <defs>
                  <linearGradient id="amberArea" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%"  stopColor="#fbbf24" stopOpacity={0.45} />
                    <stop offset="100%" stopColor="#f97316" stopOpacity={0.02} />
                  </linearGradient>
                  <linearGradient id="amberStroke" x1="0" y1="0" x2="1" y2="0">
                    <stop offset="0%"  stopColor="#fbbf24" />
                    <stop offset="100%" stopColor="#f97316" />
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
                  domain={yDomain}
                  tickFormatter={(v) => `$${formatPrice(v)}`}
                  tick={{ fill: axisTextFill, fontSize: 10 }}
                  stroke={axisColor}
                  width={78}
                />
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
                  formatter={(v: number, name: string) => {
                    if (name === "price") return [`$${formatPrice(v)}`, "Price"];
                    return [v, name];
                  }}
                />
                <Area
                  type="monotone"
                  dataKey="price"
                  stroke="url(#amberStroke)"
                  strokeWidth={1.6}
                  fill="url(#amberArea)"
                  dot={false}
                  isAnimationActive={false}
                />
                <Brush
                  dataKey="t"
                  height={22}
                  stroke="#f59e0b"
                  travellerWidth={8}
                  tickFormatter={formatTimeMs}
                  fill={isDark ? "rgba(255,255,255,0.03)" : "rgba(0,0,0,0.02)"}
                />
              </AreaChart>
            </ResponsiveContainer>
          )}
        </div>
      </div>

      {/* ── volume chart ───────────────────────────────────────── */}
      <div
        className="rounded-2xl bg-zinc-900/[0.03] dark:bg-white/[0.03] border border-zinc-900/5 dark:border-white/5 p-5 shadow-lg shadow-black/5 dark:shadow-black/20 flex flex-col"
        style={{ animation: "fadeSlideUp 0.6s ease-out both", animationDelay: "280ms", height: 220 }}
      >
        <div className="flex items-center gap-3 mb-2">
          <div className="size-8 rounded-xl bg-amber-500/10 border border-amber-500/20 flex items-center justify-center">
            <BarChart3 className="size-4 text-amber-600 dark:text-amber-400" />
          </div>
          <div className="text-[10px] uppercase tracking-[0.2em] text-zinc-500">
            Tick volume · {symbol || "—"}
          </div>
        </div>

        <div className="flex-1 mt-2 min-h-0">
          {data.length === 0 ? (
            <div className="h-full flex items-center justify-center text-sm text-zinc-500 dark:text-zinc-400">
              —
            </div>
          ) : (
            <ResponsiveContainer width="100%" height="100%">
              {/* Switched 2026-05-06 from BarChart → AreaChart with
                  step interpolation. BarChart with type="number"
                  scale="time" auto-sized bars to ~1px width when
                  there are 600+ ticks in 60 s, making them effectively
                  invisible. The step area renders the volume profile
                  cleanly with the same data, same scale. */}
              <AreaChart data={data} margin={{ top: 5, right: 12, left: 4, bottom: 0 }}>
                <defs>
                  <linearGradient id="amberVol" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%"  stopColor="#fbbf24" stopOpacity={0.9} />
                    <stop offset="100%" stopColor="#f97316" stopOpacity={0.15} />
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
                  tick={{ fill: axisTextFill, fontSize: 10 }}
                  stroke={axisColor}
                  width={56}
                  tickFormatter={(v) => v.toLocaleString()}
                />
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
                  formatter={(v: number) => [v.toLocaleString(), "Size"]}
                />
                <Area
                  type="stepAfter"
                  dataKey="volume"
                  stroke="#f59e0b"
                  strokeWidth={1}
                  fill="url(#amberVol)"
                  isAnimationActive={false}
                  dot={false}
                  activeDot={{ r: 3, fill: "#f59e0b", stroke: "#fff" }}
                />
              </AreaChart>
            </ResponsiveContainer>
          )}
        </div>
      </div>

      {stats?.truncated && (
        <div className="text-[11px] text-amber-600 dark:text-amber-400">
          Showing the first 10,000 ticks. Filter by minute or download a smaller window for tighter zoom.
        </div>
      )}
    </div>
  );
}
