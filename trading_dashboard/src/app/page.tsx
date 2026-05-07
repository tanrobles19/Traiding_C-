"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { Activity, ListOrdered, RefreshCw, ArrowRight, Building2, Gauge } from "lucide-react";

type StatsResponse = {
  counts: Record<string, number>;
  generated_at: number;
};

function formatNumber(n: number): string {
  return n.toLocaleString("en-US");
}

type TileProps = {
  label: string;
  value: string;
  href?: string;
  hint?: string;
  icon: React.ComponentType<{ className?: string }>;
  delayMs: number;
};

function StatTile({ label, value, href, hint, icon: Icon, delayMs }: TileProps) {
  const inner = (
    <div
      className="group rounded-2xl bg-zinc-900/[0.03] dark:bg-white/[0.03] border border-zinc-900/5 dark:border-white/5 p-6 shadow-lg shadow-black/5 dark:shadow-black/20 transition-all duration-500 ease-out hover:bg-zinc-900/[0.05] dark:hover:bg-white/[0.06] hover:border-zinc-900/10 dark:hover:border-white/10 hover:shadow-2xl hover:shadow-black/10 dark:hover:shadow-black/40 hover:-translate-y-1"
      style={{
        animation: `fadeSlideUp 0.6s ease-out both`,
        animationDelay: `${delayMs}ms`,
      }}
    >
      <div className="flex items-start justify-between">
        <div className="size-10 rounded-xl bg-amber-500/10 border border-amber-500/20 flex items-center justify-center">
          <Icon className="size-5 text-amber-600 dark:text-amber-400" />
        </div>
        {href && (
          <ArrowRight className="size-4 text-zinc-400 dark:text-zinc-500 transition-all duration-300 group-hover:translate-x-1 group-hover:text-amber-600 dark:group-hover:text-amber-400" />
        )}
      </div>

      <div className="mt-5 text-[10px] font-medium uppercase tracking-[0.22em] text-zinc-500">
        {label}
      </div>
      <div className="mt-2 text-3xl font-bold tabular-nums tracking-tight text-zinc-900 dark:text-white">
        {value}
      </div>
      {hint && (
        <div className="mt-2 text-xs text-zinc-500 dark:text-zinc-400">{hint}</div>
      )}
    </div>
  );
  return href ? <Link href={href}>{inner}</Link> : inner;
}

export default function Home() {
  const { data } = useQuery<StatsResponse>({
    queryKey: ["stats"],
    queryFn: async () => {
      const r = await fetch("/api/stats");
      if (!r.ok) throw new Error("stats failed");
      return r.json();
    },
    refetchInterval: 5_000,
  });

  const signals = data?.counts?.TradeSignalsBuyPerSecond ?? 0;
  const orders  = data?.counts?.Orders ?? 0;
  const stocks  = data?.counts?.Stocks ?? 0;
  const rv      = data?.counts?.RelativeVolumeRatioHour ?? 0;

  return (
    <div className="px-8 py-10 max-w-7xl mx-auto">
      <div
        style={{ animation: "fadeSlideUp 0.6s ease-out both" }}
      >
        <div className="text-[11px] uppercase tracking-[0.22em] text-zinc-500">
          Overview
        </div>
        <h1 className="mt-2 text-3xl font-bold tracking-tight text-zinc-900 dark:text-white">
          System status
        </h1>
        <div className="mt-3 h-0.5 w-16 rounded-full bg-gradient-to-r from-amber-400 to-orange-500" />
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-5 mt-10">
        <StatTile
          label="TradeSignalsBuyPerSecond"
          value={formatNumber(signals)}
          href="/signals"
          hint="Click to browse"
          icon={Activity}
          delayMs={80}
        />
        <StatTile
          label="Orders"
          value={formatNumber(orders)}
          href="/orders"
          hint="Click to browse"
          icon={ListOrdered}
          delayMs={160}
        />
        <StatTile
          label="Stocks"
          value={formatNumber(stocks)}
          href="/stocks"
          hint="Symbol registry"
          icon={Building2}
          delayMs={240}
        />
        <StatTile
          label="RelativeVolumeRatioHour"
          value={formatNumber(rv)}
          href="/rv"
          hint="Hourly volume baselines"
          icon={Gauge}
          delayMs={320}
        />
        <StatTile
          label="Refresh interval"
          value="5s"
          hint="Auto-poll across the app"
          icon={RefreshCw}
          delayMs={400}
        />
      </div>
    </div>
  );
}
