"use client";

import { ChevronFirst, ChevronLast, ChevronLeft, ChevronRight } from "lucide-react";

const navBtn =
  "size-9 inline-flex items-center justify-center rounded-full bg-zinc-900/[0.03] dark:bg-white/[0.03] border border-zinc-900/5 dark:border-white/5 text-zinc-600 dark:text-zinc-300 transition-all duration-300 hover:bg-amber-500/10 hover:text-amber-600 dark:hover:text-amber-400 hover:border-amber-500/20 active:scale-95 disabled:opacity-30 disabled:cursor-not-allowed disabled:hover:bg-zinc-900/[0.03] dark:disabled:hover:bg-white/[0.03] disabled:hover:text-zinc-600 dark:disabled:hover:text-zinc-300 disabled:hover:border-zinc-900/5 dark:disabled:hover:border-white/5";

// "All" sentinel — the selector renders this label, the wire sends a
// large finite number (50,000) which the server caps to its hard
// LIMIT in query-builder.ts. Total above 50K still paginates normally.
export const PAGE_SIZE_ALL = 50_000;

// Default options offered by the size selector. Pages can override
// via the `pageSizeOptions` prop on TablePage.
export const DEFAULT_PAGE_SIZE_OPTIONS: { value: number; label: string }[] = [
  { value: 100,            label: "100"  },
  { value: 500,            label: "500"  },
  { value: 1000,           label: "1000" },
  { value: PAGE_SIZE_ALL,  label: "All"  },
];

export function Pagination({
  page,
  pageSize,
  total,
  onPageChange,
  onPageSizeChange,
  pageSizeOptions = DEFAULT_PAGE_SIZE_OPTIONS,
}: {
  page: number;
  pageSize: number;
  total: number;
  onPageChange: (page: number) => void;
  // When provided, the selector is rendered. Omit to keep the existing
  // fixed-pageSize behavior on pages that don't need a selector.
  onPageSizeChange?: (size: number) => void;
  pageSizeOptions?: { value: number; label: string }[];
}) {
  const totalPages = Math.max(1, Math.ceil(total / pageSize));
  const from = total === 0 ? 0 : page * pageSize + 1;
  const to   = Math.min(total, (page + 1) * pageSize);

  const canPrev = page > 0;
  const canNext = page < totalPages - 1;

  return (
    <div className="flex items-center justify-between text-xs text-zinc-500 dark:text-zinc-400 px-2">
      <div className="flex items-center gap-3">
        <div className="font-mono tabular-nums">
          {from.toLocaleString()}–{to.toLocaleString()}
          <span className="text-zinc-400 dark:text-zinc-600"> · of </span>
          <span className="text-zinc-700 dark:text-zinc-200">{total.toLocaleString()}</span>
        </div>

        {onPageSizeChange && (
          <label className="flex items-center gap-1.5 font-mono">
            <span className="text-zinc-400 dark:text-zinc-600">rows</span>
            <select
              value={pageSize}
              onChange={(e) => onPageSizeChange(Number(e.target.value))}
              className="h-7 px-2 rounded-lg bg-zinc-900/[0.03] dark:bg-white/[0.03] border border-zinc-900/5 dark:border-white/5 text-zinc-700 dark:text-zinc-200 cursor-pointer hover:bg-amber-500/10 hover:border-amber-500/20 transition-colors focus:outline-none focus:ring-2 focus:ring-amber-500/30"
              aria-label="Rows per page"
            >
              {pageSizeOptions.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </select>
          </label>
        )}
      </div>

      <div className="flex items-center gap-1.5">
        <button className={navBtn} disabled={!canPrev} onClick={() => onPageChange(0)}            aria-label="first">
          <ChevronFirst className="size-4" />
        </button>
        <button className={navBtn} disabled={!canPrev} onClick={() => onPageChange(page - 1)}     aria-label="previous">
          <ChevronLeft className="size-4" />
        </button>

        <div className="font-mono tabular-nums px-3 py-1.5 rounded-full bg-amber-500/10 border border-amber-500/20 text-amber-700 dark:text-amber-300">
          {page + 1} / {totalPages}
        </div>

        <button className={navBtn} disabled={!canNext} onClick={() => onPageChange(page + 1)}     aria-label="next">
          <ChevronRight className="size-4" />
        </button>
        <button className={navBtn} disabled={!canNext} onClick={() => onPageChange(totalPages - 1)} aria-label="last">
          <ChevronLast className="size-4" />
        </button>
      </div>
    </div>
  );
}
