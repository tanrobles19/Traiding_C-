"use client";

import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Activity, ListOrdered, Building2, Gauge } from "lucide-react";
import { ThemeToggle } from "@/components/ThemeToggle";

type StatsResponse = {
  counts: Record<string, number>;
  generated_at: number;
};

function formatClock(d: Date): string {
  return d.toLocaleTimeString("en-US", { hour12: false });
}

function formatNumber(n: number): string {
  return n.toLocaleString("en-US");
}

function CountPill({
  label,
  value,
  icon: Icon,
}: {
  label: string;
  value: string;
  icon: React.ComponentType<{ className?: string }>;
}) {
  return (
    <div className="flex items-center gap-2 px-3 py-1.5 rounded-full bg-zinc-900/[0.03] dark:bg-white/[0.03] border border-zinc-900/5 dark:border-white/5">
      <Icon className="size-3.5 text-amber-500 dark:text-amber-400" />
      <span className="text-zinc-500 dark:text-zinc-400">{label}</span>
      <span className="font-mono tabular-nums text-zinc-900 dark:text-zinc-100">{value}</span>
    </div>
  );
}

export function Header() {
  const [now, setNow] = useState(() => new Date());

  useEffect(() => {
    const id = setInterval(() => setNow(new Date()), 1_000);
    return () => clearInterval(id);
  }, []);

  const { data, isFetching, isError } = useQuery<StatsResponse>({
    queryKey: ["stats"],
    queryFn: async () => {
      const r = await fetch("/api/stats");
      if (!r.ok) throw new Error("stats failed");
      return r.json();
    },
    refetchInterval: 5_000,
  });

  const signalsCount = data?.counts?.TradeSignalsBuyPerSecond ?? 0;
  const ordersCount  = data?.counts?.Orders ?? 0;
  const stocksCount  = data?.counts?.Stocks ?? 0;
  const rvCount      = data?.counts?.RelativeVolumeRatioHour ?? 0;

  const dotClass = isError
    ? "bg-red-500"
    : isFetching
    ? "bg-amber-400 animate-pulse"
    : "bg-emerald-400";

  return (
    <header className="sticky top-0 z-10 backdrop-blur-md bg-white/70 dark:bg-zinc-950/70 border-b border-zinc-900/5 dark:border-white/5 flex items-center px-6 h-14 gap-6">
      <div className="text-[11px] uppercase tracking-[0.22em] text-zinc-500 dark:text-zinc-500">
        Trading Signals · Orders
      </div>

      <div className="ml-auto flex items-center gap-3 text-xs">
        <CountPill label="Signals" value={formatNumber(signalsCount)} icon={Activity}    />
        <CountPill label="Orders"  value={formatNumber(ordersCount)}  icon={ListOrdered} />
        <CountPill label="Stocks"  value={formatNumber(stocksCount)}  icon={Building2}   />
        <CountPill label="RV"      value={formatNumber(rvCount)}      icon={Gauge}       />

        <div className="flex items-center gap-2 px-3 py-1.5 rounded-full bg-zinc-900/[0.03] dark:bg-white/[0.03] border border-zinc-900/5 dark:border-white/5">
          <span className={`size-2 rounded-full ${dotClass}`} />
          <span className="text-zinc-500 dark:text-zinc-400">live</span>
          <span className="font-mono tabular-nums text-zinc-900 dark:text-zinc-100">{formatClock(now)}</span>
        </div>

        <ThemeToggle />
      </div>
    </header>
  );
}
