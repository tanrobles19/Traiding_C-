"use client";

import { useMemo } from "react";
import { BarChart3 } from "lucide-react";
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, CartesianGrid, ResponsiveContainer,
} from "recharts";
import { useTheme } from "@/components/ThemeProvider";

export function SymbolBarChart<TRow extends { symbol?: string | null }>({
  rows,
  topN = 10,
  title,
}: {
  rows: TRow[];
  topN?: number;
  title: string;
}) {
  const { theme } = useTheme();

  const data = useMemo(() => {
    const counts = new Map<string, number>();
    for (const r of rows) {
      const s = (r.symbol ?? "").toString();
      if (!s) continue;
      counts.set(s, (counts.get(s) ?? 0) + 1);
    }
    const arr = Array.from(counts.entries()).map(([symbol, count]) => ({ symbol, count }));
    arr.sort((a, b) => b.count - a.count);
    return arr.slice(0, topN);
  }, [rows, topN]);

  const isDark = theme === "dark";
  const gridColor    = isDark ? "rgba(255,255,255,0.05)" : "rgba(0,0,0,0.06)";
  const axisColor    = isDark ? "rgba(255,255,255,0.1)"  : "rgba(0,0,0,0.1)";
  const axisTextFill = isDark ? "#a1a1aa" : "#52525b";
  const tooltipBg    = isDark ? "#18181b" : "#ffffff";
  const tooltipText  = isDark ? "#fafafa" : "#18181b";
  const tooltipBdr   = isDark ? "rgba(255,255,255,0.1)" : "rgba(0,0,0,0.08)";

  return (
    <div className="rounded-2xl bg-zinc-900/[0.03] dark:bg-white/[0.03] border border-zinc-900/5 dark:border-white/5 p-5 h-72 flex flex-col shadow-lg shadow-black/5 dark:shadow-black/20">
      <div className="flex items-center gap-3 mb-2">
        <div className="size-8 rounded-xl bg-amber-500/10 border border-amber-500/20 flex items-center justify-center">
          <BarChart3 className="size-4 text-amber-600 dark:text-amber-400" />
        </div>
        <div className="text-[10px] uppercase tracking-[0.2em] text-zinc-500">
          {title}
        </div>
      </div>

      <div className="flex-1 mt-2 min-h-0">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
            <defs>
              <linearGradient id="amberBar" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%"  stopColor="#fbbf24" stopOpacity={1} />
                <stop offset="100%" stopColor="#f97316" stopOpacity={1} />
              </linearGradient>
            </defs>
            <CartesianGrid stroke={gridColor} strokeDasharray="2 4" vertical={false} />
            <XAxis
              dataKey="symbol"
              tick={{ fill: axisTextFill, fontSize: 10 }}
              stroke={axisColor}
            />
            <YAxis
              tick={{ fill: axisTextFill, fontSize: 10 }}
              stroke={axisColor}
              width={28}
              allowDecimals={false}
            />
            <Tooltip
              cursor={{ fill: gridColor }}
              contentStyle={{
                background: tooltipBg,
                border: `1px solid ${tooltipBdr}`,
                borderRadius: 12,
                fontSize: 12,
                color: tooltipText,
                boxShadow: "0 10px 40px rgba(0,0,0,0.2)",
              }}
              labelStyle={{ color: axisTextFill }}
            />
            <Bar dataKey="count" fill="url(#amberBar)" radius={[6, 6, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
