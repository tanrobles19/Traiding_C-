"use client";

import { useState, type ReactNode } from "react";
import { useQuery, keepPreviousData } from "@tanstack/react-query";
import { Loader2 } from "lucide-react";
import { DataGrid } from "@/components/DataGrid";
import {
  PORTFOLIO_HELD_COLUMNS,
  PORTFOLIO_SOLD_COLUMNS,
  type ColumnDef,
} from "@/lib/tables";
import type { Filter, SortDir } from "@/lib/query-builder";

type PortfolioRow = Record<string, unknown>;

type ApiResponse = { rows: PortfolioRow[]; total: number };

// /portfolio
//
// Two stacked grids on the same page:
//
//   1) HELD  → /api/portfolio       — refetches every 5 s with live
//                                      `last_price` from Polygon.
//   2) SOLD  → /api/portfolio/sold  — fetched ONCE on mount, frozen.
//                                      Historical exit log; no
//                                      polling, no Polygon enrichment.
export default function PortfolioPage() {
  return (
    <div className="flex flex-col h-full px-6 py-6 gap-8 overflow-auto max-w-[120rem] mx-auto w-full">
      <HeldSection />
      <SoldSection />
    </div>
  );
}

function HeldSection() {
  const [filters, setFilters] = useState<Filter[]>([]);
  const [sort, setSort] = useState<{ column: string; dir: SortDir } | undefined>(undefined);

  const { data, isFetching, error } = useQuery<ApiResponse>({
    queryKey: ["/api/portfolio", filters, sort],
    queryFn: async () => {
      const params = new URLSearchParams({ pageSize: "500" });
      if (filters.length > 0) params.set("filters", JSON.stringify(filters));
      if (sort)               params.set("sort",    JSON.stringify(sort));
      const r = await fetch(`/api/portfolio?${params.toString()}`);
      if (!r.ok) throw new Error(`fetch /api/portfolio failed (${r.status})`);
      return r.json();
    },
    refetchInterval: 5_000,
    placeholderData: keepPreviousData,
  });

  const rows  = data?.rows ?? [];
  const total = data?.total ?? 0;

  return (
    <Section
      eyebrow="Snapshot taken at C++ trader startup. Last and % refresh every 5 seconds via Polygon."
      title="My Portfolio — IB account positions"
      isFetching={isFetching}
      total={total}
      error={error as Error | null}
      gridHeight="h-[28rem]"
      columns={PORTFOLIO_HELD_COLUMNS}
      rows={rows}
      onFilterChange={setFilters}
      onSortChange={setSort}
    />
  );
}

function SoldSection() {
  const { data, isFetching, error } = useQuery<ApiResponse>({
    queryKey: ["/api/portfolio/sold"],
    queryFn: async () => {
      const r = await fetch("/api/portfolio/sold?pageSize=500");
      if (!r.ok) throw new Error(`fetch /api/portfolio/sold failed (${r.status})`);
      return r.json();
    },
    refetchInterval: false,
    refetchOnWindowFocus: false,
    placeholderData: keepPreviousData,
  });

  const rows  = data?.rows ?? [];
  const total = data?.total ?? 0;

  return (
    <Section
      eyebrow="Historical — frozen at fetch time. Does not auto-refresh."
      title="Sold positions — session history"
      isFetching={isFetching}
      total={total}
      error={error as Error | null}
      gridHeight="h-[22rem]"
      columns={PORTFOLIO_SOLD_COLUMNS}
      rows={rows}
    />
  );
}

function Section({
  eyebrow,
  title,
  isFetching,
  total,
  error,
  gridHeight,
  columns,
  rows,
  onFilterChange,
  onSortChange,
}: {
  eyebrow: string;
  title: string;
  isFetching: boolean;
  total: number;
  error: Error | null;
  gridHeight: string;
  columns: ColumnDef[];
  rows: PortfolioRow[];
  onFilterChange?: (filters: Filter[]) => void;
  onSortChange?: (sort: { column: string; dir: SortDir } | undefined) => void;
}): ReactNode {
  return (
    <div
      className="flex flex-col gap-4"
      style={{ animation: "fadeSlideUp 0.6s ease-out both" }}
    >
      <div className="flex items-end justify-between">
        <div>
          <div className="text-[11px] uppercase tracking-[0.22em] text-zinc-500">
            {eyebrow}
          </div>
          <h1 className="mt-2 text-3xl font-bold tracking-tight text-zinc-900 dark:text-white">
            {title}
          </h1>
          <div className="mt-3 h-0.5 w-16 rounded-full bg-gradient-to-r from-amber-400 to-orange-500" />
        </div>
        <div className="flex items-center gap-2 text-xs text-zinc-500 dark:text-zinc-400 tabular-nums">
          {isFetching && <Loader2 className="size-3.5 animate-spin text-amber-500 dark:text-amber-400" />}
          {isFetching ? "fetching…" : `${total.toLocaleString()} rows`}
        </div>
      </div>

      {error ? (
        <div className="rounded-xl bg-red-500/10 border border-red-500/20 px-4 py-3 text-sm text-red-600 dark:text-red-400">
          Error: {error.message}
        </div>
      ) : (
        <div className={`${gridHeight} rounded-2xl bg-zinc-900/[0.03] dark:bg-white/[0.03] border border-zinc-900/5 dark:border-white/5 overflow-hidden shadow-lg shadow-black/5 dark:shadow-black/20`}>
          <DataGrid<PortfolioRow>
            rows={rows}
            columns={columns}
            onFilterChange={onFilterChange}
            onSortChange={onSortChange}
          />
        </div>
      )}
    </div>
  );
}
