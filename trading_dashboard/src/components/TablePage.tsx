"use client";

import { useState, type ReactNode } from "react";
import { useQuery, keepPreviousData, useQueryClient } from "@tanstack/react-query";
import { Loader2, Trash2 } from "lucide-react";
import { DataGrid, type RowAction } from "@/components/DataGrid";
import { Pagination, DEFAULT_PAGE_SIZE_OPTIONS } from "@/components/Pagination";
import { ConfirmDialog } from "@/components/ConfirmDialog";
import type { ColumnDef } from "@/lib/tables";
import type { Filter, SortDir } from "@/lib/query-builder";

type ApiResponse<TRow> = {
  rows: TRow[];
  total: number;
  page: number;
  pageSize: number;
};

export function TablePage<TRow>({
  title,
  description,
  apiPath,
  columns,
  renderChart,
  renderSidePanel,
  clearEndpoint,
  toolbarExtra,
  rowAction,
  showPageSizeSelector = false,
  pageSizeOptions = DEFAULT_PAGE_SIZE_OPTIONS,
  initialPageSize = 100,
  getRowClass,
  getCellPrefix,
  bottomPanel,
}: {
  title: string;
  description: string;
  apiPath: string;
  columns: ColumnDef[];
  // Right-side chart slot — fixed 320px column. Receives the current
  // page's rows (already paginated).
  renderChart?: (rows: TRow[]) => ReactNode;
  // Right-side info slot — fixed 320px column. Use for summary panels
  // (e.g. Raw Trades' OHLC + symbol stats). Receives the current rows
  // and the loaded total so the panel can describe the underlying data.
  renderSidePanel?: (rows: TRow[], total: number) => ReactNode;
  clearEndpoint?: string;
  toolbarExtra?: ReactNode;
  rowAction?: RowAction<TRow>;
  // When true, the Pagination footer renders a rows-per-page <select>
  // and pageSize becomes mutable. Off by default — most pages stay on
  // 100 rows. Turn on for downloader-style pages (Raw Trades).
  showPageSizeSelector?: boolean;
  pageSizeOptions?: { value: number; label: string }[];
  initialPageSize?: number;
  // Per-row class function. Receives (row, allRows) so the page can
  // make whole-page decisions (e.g. OHLC: which row sets the OPEN
  // depends on the full sequence). Used by /raw-trades to tint the
  // OHLC-determining ticks green.
  getRowClass?: (row: TRow, allRows: TRow[]) => string | null | undefined;
  // Per-cell prefix injector — same currying as getRowClass. Returns
  // optional JSX to prepend inside a specific (row, columnKey) cell.
  // Used by /raw-trades to put an "OPEN" badge inside the Price cell
  // of the candle-open row.
  getCellPrefix?: (row: TRow, allRows: TRow[], columnKey: string) => ReactNode | null | undefined;
  // Optional content rendered BELOW the main table + pagination, inside
  // the same scrollable page wrapper. When provided, the page becomes
  // vertically scrollable and the main grid switches from "fill all
  // available height" to a tall fixed height so the bottom panel has
  // room. Used by /raw-trades to stack a Quotes grid below the Trades
  // grid. When undefined the page keeps its original single-grid
  // behaviour.
  bottomPanel?: ReactNode;
}) {
  const queryClient = useQueryClient();
  const [page, setPage] = useState(0);
  const [pageSize, setPageSize] = useState(initialPageSize);
  const [filters, setFilters] = useState<Filter[]>([]);
  const [sort, setSort] = useState<{ column: string; dir: SortDir } | undefined>(undefined);

  async function clearTable() {
    if (!clearEndpoint) return;
    const r = await fetch(clearEndpoint, { method: "POST" });
    if (!r.ok) {
      const body = await r.json().catch(() => ({}));
      throw new Error(body.error ?? `clear failed (${r.status})`);
    }
    setPage(0);
    setFilters([]);
    await queryClient.invalidateQueries({ queryKey: [apiPath] });
    await queryClient.invalidateQueries({ queryKey: ["stats"] });
  }

  const { data, isFetching, error } = useQuery<ApiResponse<TRow>>({
    queryKey: [apiPath, page, pageSize, filters, sort],
    queryFn: async () => {
      const params = new URLSearchParams({
        page: String(page),
        pageSize: String(pageSize),
      });
      if (filters.length > 0) params.set("filters", JSON.stringify(filters));
      if (sort)               params.set("sort",    JSON.stringify(sort));
      const r = await fetch(`${apiPath}?${params.toString()}`);
      if (!r.ok) throw new Error(`fetch ${apiPath} failed (${r.status})`);
      return r.json();
    },
    refetchInterval: 5_000,
    placeholderData: keepPreviousData,
  });

  const rows = data?.rows ?? [];
  const total = data?.total ?? 0;

  // When a bottom panel is provided, the page must become scrollable
  // and the main grid needs a definite height (instead of flex-1 fill)
  // so the bottom panel can render below it.
  const hasBottomPanel = bottomPanel != null;
  const wrapperOverflow = hasBottomPanel ? "overflow-y-auto" : "overflow-hidden";
  const gridSectionFlex = hasBottomPanel ? "h-[40rem]" : "flex-1 min-h-0";

  return (
    <div className={`flex flex-col h-full px-6 py-6 gap-5 ${wrapperOverflow} max-w-[120rem] mx-auto w-full`}>
      <div
        className="flex items-end justify-between"
        style={{ animation: "fadeSlideUp 0.6s ease-out both" }}
      >
        <div>
          <div className="text-[11px] uppercase tracking-[0.22em] text-zinc-500">
            {description}
          </div>
          <h1 className="mt-2 text-3xl font-bold tracking-tight text-zinc-900 dark:text-white">
            {title}
          </h1>
          <div className="mt-3 h-0.5 w-16 rounded-full bg-gradient-to-r from-amber-400 to-orange-500" />
        </div>
        <div className="flex items-center gap-3">
          {toolbarExtra}

          {clearEndpoint && (
            <ConfirmDialog
              title={`Clear ${description}?`}
              description={
                <span>
                  This permanently deletes every row in{" "}
                  <span className="font-mono">{description}</span>{" "}
                  ({total.toLocaleString()} currently). This action cannot be undone.
                </span>
              }
              confirmLabel="Clear table"
              onConfirm={clearTable}
              trigger={
                <button
                  className="inline-flex items-center gap-2 px-4 h-9 rounded-xl bg-red-500/10 border border-red-500/20 text-sm font-medium text-red-600 dark:text-red-400 transition-all duration-300 hover:bg-red-500/20 hover:border-red-500/40 active:scale-[0.97]"
                  title="Truncate this table"
                >
                  <Trash2 className="size-4" />
                  Clear table
                </button>
              }
            />
          )}

          <div className="flex items-center gap-2 text-xs text-zinc-500 dark:text-zinc-400 tabular-nums">
            {isFetching && <Loader2 className="size-3.5 animate-spin text-amber-500 dark:text-amber-400" />}
            {isFetching ? "fetching…" : `${total.toLocaleString()} rows`}
          </div>
        </div>
      </div>

      <div
        className={`grid grid-cols-1 ${renderChart || renderSidePanel ? "xl:grid-cols-[1fr_320px]" : ""} gap-5 ${gridSectionFlex}`}
        style={{ animation: "fadeSlideUp 0.6s ease-out both", animationDelay: "120ms" }}
      >
        <div className="flex flex-col gap-4 min-h-0">
          {error ? (
            <div className="rounded-xl bg-red-500/10 border border-red-500/20 px-4 py-3 text-sm text-red-600 dark:text-red-400">
              Error: {(error as Error).message}
            </div>
          ) : (
            <div className="flex-1 min-h-0 rounded-2xl bg-zinc-900/[0.03] dark:bg-white/[0.03] border border-zinc-900/5 dark:border-white/5 overflow-hidden shadow-lg shadow-black/5 dark:shadow-black/20">
              <DataGrid<TRow>
                rows={rows}
                columns={columns}
                rowAction={rowAction}
                getRowClass={
                  getRowClass
                    ? (row) => getRowClass(row, rows)
                    : undefined
                }
                getCellPrefix={
                  getCellPrefix
                    ? (row, columnKey) => getCellPrefix(row, rows, columnKey)
                    : undefined
                }
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
            onPageSizeChange={
              showPageSizeSelector
                ? (size) => {
                    setPageSize(size);
                    setPage(0);
                  }
                : undefined
            }
            pageSizeOptions={pageSizeOptions}
          />
        </div>

        {(renderChart || renderSidePanel) && (
          <div className="flex flex-col gap-4">
            {renderSidePanel?.(rows, total)}
            {renderChart?.(rows)}
          </div>
        )}
      </div>

      {bottomPanel}
    </div>
  );
}
