"use client";

import { useEffect, useState } from "react";
import { useQuery, keepPreviousData } from "@tanstack/react-query";
import { Loader2, Filter, Settings2, BookOpen } from "lucide-react";
import { DataGrid } from "@/components/DataGrid";
import { Pagination } from "@/components/Pagination";
import {
  LOW_FLOAT_COLUMNS,
  LOW_FLOAT_MAX_VALUE_FALLBACK,
} from "@/lib/tables";
import type { Filter as FilterType, SortDir } from "@/lib/query-builder";

// /low-float
//
// Pre-filtered Stocks view: float < trading_config.low_float_threshold
// AND price within the configured range. Mirrors the legacy Python
// `get_low_float_stocks()` scanner in get_float.py.

type LowFloatRow = {
  id: number | null;
  ticker: string | null;
  close: number | string | null;
  float_value: number | null;
  short_percent_float: number | null;
  shares_outstanding: number | null;
  shares_short: number | null;
  avg_month_volume: number | null;
};

type ApiResponse = {
  rows: LowFloatRow[];
  total: number;
  page: number;
  pageSize: number;
};

type TradingConfig = {
  min_price?: number;
  max_price?: number;
  low_float_threshold?: number;
};

export default function LowFloatPage() {
  const [page, setPage] = useState(0);
  const [pageSize] = useState(100);
  const [filters, setFilters] = useState<FilterType[]>([]);
  const [sort, setSort] = useState<{ column: string; dir: SortDir } | undefined>(undefined);

  // Read trading_config.json for the active filter values — purely for
  // the side panel + banner. The route handler reads the same file
  // server-side and is the source of truth for the actual SQL filter.
  const [cfg, setCfg] = useState<TradingConfig | null>(null);
  useEffect(() => {
    fetch("/api/config")
      .then((r) => (r.ok ? r.json() : null))
      .then((c: TradingConfig | null) => setCfg(c))
      .catch(() => setCfg(null));
  }, []);

  const { data, isFetching, error } = useQuery<ApiResponse>({
    queryKey: ["/api/low-float", page, pageSize, filters, sort],
    queryFn: async () => {
      const params = new URLSearchParams({
        page: String(page),
        pageSize: String(pageSize),
      });
      if (filters.length > 0) params.set("filters", JSON.stringify(filters));
      if (sort) params.set("sort", JSON.stringify(sort));
      const r = await fetch(`/api/low-float?${params.toString()}`);
      if (!r.ok) throw new Error(`fetch /api/low-float failed (${r.status})`);
      return r.json();
    },
    refetchInterval: 5_000,
    placeholderData: keepPreviousData,
  });

  const rows  = data?.rows ?? [];
  const total = data?.total ?? 0;

  const minPrice = typeof cfg?.min_price           === "number" ? cfg.min_price           : null;
  const maxPrice = typeof cfg?.max_price           === "number" ? cfg.max_price           : null;
  const floatMax = typeof cfg?.low_float_threshold === "number" ? cfg.low_float_threshold : LOW_FLOAT_MAX_VALUE_FALLBACK;

  return (
    <div className="flex flex-col h-full px-6 py-6 gap-5 overflow-hidden max-w-[120rem] mx-auto w-full">
      <div
        className="flex items-end justify-between"
        style={{ animation: "fadeSlideUp 0.6s ease-out both" }}
      >
        <div>
          <div className="text-[11px] uppercase tracking-[0.22em] text-zinc-500">
            Strategy scanner — primary universe for the low-float momentum strategy
          </div>
          <h1 className="mt-2 text-3xl font-bold tracking-tight text-zinc-900 dark:text-white">
            Low Float Stocks — strategy candidates
          </h1>
          <div className="mt-3 h-0.5 w-16 rounded-full bg-gradient-to-r from-amber-400 to-orange-500" />
        </div>
        <div className="flex items-center gap-2 text-xs text-zinc-500 dark:text-zinc-400 tabular-nums">
          {isFetching && <Loader2 className="size-3.5 animate-spin text-amber-500 dark:text-amber-400" />}
          {isFetching ? "fetching…" : `${total.toLocaleString()} candidates`}
        </div>
      </div>

      <div
        className="rounded-xl bg-amber-500/5 border border-amber-500/20 px-4 py-3 text-sm flex items-center gap-3 flex-wrap"
        style={{ animation: "fadeSlideUp 0.6s ease-out both", animationDelay: "80ms" }}
      >
        <Filter className="size-4 text-amber-600 dark:text-amber-400 shrink-0" />
        <span className="text-zinc-500 dark:text-zinc-400 text-xs uppercase tracking-wider">
          Active filters from trading_config.json
        </span>
        <span className="font-mono tabular-nums text-zinc-900 dark:text-zinc-100">
          0 &lt; float &lt; {floatMax.toLocaleString()}
        </span>
        <span className="text-zinc-400 dark:text-zinc-600">·</span>
        <span className="font-mono tabular-nums text-zinc-900 dark:text-zinc-100">
          {minPrice !== null && maxPrice !== null
            ? `$${minPrice.toFixed(2)} ≤ price ≤ $${maxPrice.toFixed(2)}`
            : "price range from trading_config.json"}
        </span>
        <span className="text-zinc-400 dark:text-zinc-600 ml-auto text-xs">
          edit on the Data Pipeline page
        </span>
      </div>

      <div
        className="grid grid-cols-1 xl:grid-cols-[1fr_280px] gap-5 flex-1 min-h-0"
        style={{ animation: "fadeSlideUp 0.6s ease-out both", animationDelay: "160ms" }}
      >
        <div className="flex flex-col gap-4 min-h-0">
          {error ? (
            <div className="rounded-xl bg-red-500/10 border border-red-500/20 px-4 py-3 text-sm text-red-600 dark:text-red-400">
              Error: {(error as Error).message}
            </div>
          ) : (
            <div className="flex-1 min-h-0 rounded-2xl bg-zinc-900/[0.03] dark:bg-white/[0.03] border border-zinc-900/5 dark:border-white/5 overflow-hidden shadow-lg shadow-black/5 dark:shadow-black/20">
              <DataGrid<LowFloatRow>
                rows={rows}
                columns={LOW_FLOAT_COLUMNS}
                showIndex
                indexOffset={page * pageSize}
                onFilterChange={(next) => {
                  setFilters(next);
                  setPage(0);
                }}
                onSortChange={(next) => {
                  setSort(next);
                  setPage(0);
                }}
              />
            </div>
          )}

          <Pagination
            page={page}
            pageSize={pageSize}
            total={total}
            onPageChange={setPage}
          />
        </div>

        <div className="flex flex-col gap-4">
          <FilterSummaryPanel
            minPrice={minPrice}
            maxPrice={maxPrice}
            floatMax={floatMax}
            total={total}
            isFetching={isFetching}
          />
          <GlossaryPanel />
        </div>
      </div>
    </div>
  );
}

// Right-side summary panel — shows the variables that produced the
// rows currently in the grid. Mirrors the same /api/config values the
// route handler used server-side, so the operator can verify at a
// glance "this is what the table is filtering on right now".
function FilterSummaryPanel({
  minPrice,
  maxPrice,
  floatMax,
  total,
  isFetching,
}: {
  minPrice: number | null;
  maxPrice: number | null;
  floatMax: number;
  total: number;
  isFetching: boolean;
}) {
  const fmtFloat = floatMax.toLocaleString("en-US");
  const fmtPrice = (n: number | null) =>
    n === null ? "—" : `$${n.toFixed(2)}`;

  return (
    <div
      className="rounded-2xl bg-zinc-900/[0.03] dark:bg-white/[0.03] border border-zinc-900/5 dark:border-white/5 p-5 shadow-lg shadow-black/5 dark:shadow-black/20 self-start"
    >
      <div className="flex items-center gap-3 mb-4">
        <div className="size-9 rounded-xl bg-amber-500/10 border border-amber-500/20 flex items-center justify-center shrink-0">
          <Settings2 className="size-4 text-amber-600 dark:text-amber-400" />
        </div>
        <div>
          <div className="text-[10px] uppercase tracking-[0.2em] text-zinc-500">
            Filter summary
          </div>
          <div className="text-sm font-semibold text-zinc-900 dark:text-white">
            Variables driving this table
          </div>
        </div>
      </div>

      <dl className="space-y-3 text-sm">
        <Row label="Min Price"            value={fmtPrice(minPrice)} />
        <Row label="Max Price"            value={fmtPrice(maxPrice)} />
        <Row label="Low Float Threshold"  value={`${fmtFloat} sh`}    hint="float must be strictly less than this" />
        <Row label="Float floor"          value="0"                   hint="excludes NULL / 0 (yfinance failures)" />
      </dl>

      <div className="mt-4 pt-4 border-t border-zinc-900/5 dark:border-white/5 space-y-1.5">
        <div className="flex items-baseline justify-between text-sm">
          <span className="text-zinc-500 dark:text-zinc-400">Candidates</span>
          <span className="font-mono tabular-nums text-zinc-900 dark:text-zinc-100 font-semibold">
            {isFetching ? (
              <Loader2 className="size-3.5 animate-spin inline text-amber-500" />
            ) : (
              total.toLocaleString()
            )}
          </span>
        </div>
        <div className="text-[11px] text-zinc-500 dark:text-zinc-400">
          Sorted by Short % desc · refreshes every 5 s
        </div>
      </div>

      <div className="mt-4 text-[11px] text-zinc-500 dark:text-zinc-500">
        Source of truth: <span className="font-mono">trading_config.json</span>.
        Edit on the Data Pipeline page.
      </div>
    </div>
  );
}

function Row({
  label,
  value,
  hint,
}: {
  label: string;
  value: string;
  hint?: string;
}) {
  return (
    <div>
      <div className="flex items-baseline justify-between gap-3">
        <dt className="text-zinc-500 dark:text-zinc-400">{label}</dt>
        <dd className="font-mono tabular-nums text-zinc-900 dark:text-zinc-100">
          {value}
        </dd>
      </div>
      {hint && (
        <div className="text-[11px] text-zinc-400 dark:text-zinc-600 mt-0.5">
          {hint}
        </div>
      )}
    </div>
  );
}

// Right-side glossary — lives below the FilterSummaryPanel. Plain
// text explanations of the strategy-relevant metrics so an operator
// reading the table for the first time understands what each column
// means without leaving the page.
function GlossaryPanel() {
  const terms: { term: string; body: string }[] = [
    {
      term: "Float",
      body: "Shares actually available for the public to buy/sell. Excludes insider holdings, restricted stock, and lockups. A small float means limited supply — any wave of demand moves the price sharply. The strategy targets float < 10M.",
    },
    {
      term: "Shares Outstanding",
      body: "Total shares the company has issued (float + restricted/insider). Denominator of Short %. Compare with Float — the gap is what's locked up in insider hands.",
    },
    {
      term: "Short %",
      body: "Shares Short ÷ Shares Outstanding × 100. Measures bearish pressure on the stock. > 10% (green check) = short-squeeze candidate: if price rises, shorts are forced to cover, amplifying the upside move.",
    },
  ];

  return (
    <div className="rounded-2xl bg-zinc-900/[0.03] dark:bg-white/[0.03] border border-zinc-900/5 dark:border-white/5 p-5 shadow-lg shadow-black/5 dark:shadow-black/20">
      <div className="flex items-center gap-3 mb-4">
        <div className="size-9 rounded-xl bg-amber-500/10 border border-amber-500/20 flex items-center justify-center shrink-0">
          <BookOpen className="size-4 text-amber-600 dark:text-amber-400" />
        </div>
        <div>
          <div className="text-[10px] uppercase tracking-[0.2em] text-zinc-500">
            Glossary
          </div>
          <div className="text-sm font-semibold text-zinc-900 dark:text-white">
            How to read the table
          </div>
        </div>
      </div>

      <div className="space-y-4">
        {terms.map((t) => (
          <div key={t.term}>
            <div className="text-sm font-semibold text-zinc-900 dark:text-zinc-100">
              {t.term}
            </div>
            <div className="text-[12px] leading-relaxed text-zinc-500 dark:text-zinc-400 mt-1">
              {t.body}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
