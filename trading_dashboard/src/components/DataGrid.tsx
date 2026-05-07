"use client";

import { useEffect, useMemo, useRef, type ReactNode } from "react";
import { AgGridReact } from "ag-grid-react";
import {
  AllCommunityModule,
  ModuleRegistry,
  themeQuartz,
  colorSchemeDark,
  colorSchemeLight,
} from "ag-grid-community";
import type {
  ColDef,
  RowClassParams,
  SortChangedEvent,
  FilterChangedEvent,
} from "ag-grid-community";
import { AlertTriangle, OctagonAlert, CheckCircle2, TrendingUp, TrendingDown } from "lucide-react";
import type { ColumnDef } from "@/lib/tables";
import type { Filter, SortDir } from "@/lib/query-builder";
import { formatterFor } from "@/lib/format";
import { useTheme } from "@/components/ThemeProvider";

ModuleRegistry.registerModules([AllCommunityModule]);

// Premium-UI palette mapped onto AG Grid theme params.
// Both schemes use a transparent surface so the table sits cleanly on
// top of its glass card, and an amber-tinted row-hover that matches the
// rest of the dashboard.
const lightTheme = themeQuartz.withPart(colorSchemeLight).withParams({
  backgroundColor: "transparent",
  foregroundColor: "#18181b",
  headerBackgroundColor: "rgba(0,0,0,0.02)",
  headerTextColor: "#71717a",
  borderColor: "rgba(0,0,0,0.05)",
  rowHoverColor: "rgba(245,158,11,0.06)",
  oddRowBackgroundColor: "transparent",
  fontFamily: "var(--font-sans)",
  fontSize: 12,
  cellTextColor: "#18181b",
});

const darkTheme = themeQuartz.withPart(colorSchemeDark).withParams({
  backgroundColor: "transparent",
  foregroundColor: "#fafafa",
  headerBackgroundColor: "rgba(255,255,255,0.03)",
  headerTextColor: "#a1a1aa",
  borderColor: "rgba(255,255,255,0.05)",
  rowHoverColor: "rgba(245,158,11,0.08)",
  oddRowBackgroundColor: "transparent",
  fontFamily: "var(--font-sans)",
  fontSize: 12,
  cellTextColor: "#fafafa",
});

export type RowAction<TRow> = {
  width?: number;
  render: (row: TRow) => ReactNode;
};

// Map AG Grid filter "type" strings to our backend's `Filter.op` values.
const TEXT_OP_MAP: Record<string, Filter["op"]> = {
  equals:     "eq",
  notEqual:   "ne",
  contains:   "contains",
  notContains:"contains",   // best-effort; backend treats both as LIKE %
  startsWith: "starts",
  endsWith:   "ends",
};
const NUMBER_OP_MAP: Record<string, Filter["op"]> = {
  equals:             "eq",
  notEqual:           "ne",
  lessThan:           "lt",
  lessThanOrEqual:    "le",
  greaterThan:        "gt",
  greaterThanOrEqual: "ge",
};

function isNumericLike(t: ColumnDef["type"]): boolean {
  return (
    t === "number" ||
    t === "number_abbreviated" ||
    t === "decimal" ||
    t === "datetime_ms" ||
    t === "datetime_double_seconds" ||
    t === "datetime_decimal_seconds"
  );
}

export function DataGrid<TRow>({
  rows,
  columns,
  rowAction,
  onFilterChange,
  onSortChange,
  showIndex = false,
  indexOffset = 0,
  getRowClass,
  getCellPrefix,
}: {
  rows: TRow[];
  columns: ColumnDef[];
  rowAction?: RowAction<TRow>;
  onFilterChange?: (filters: Filter[]) => void;
  onSortChange?: (sort: { column: string; dir: SortDir } | undefined) => void;
  // Prepend a "#" column with row numbers (1, 2, 3, …). Pinned left,
  // not sortable / filterable. Useful as a visual row counter on
  // strategy-focused tables (e.g. /low-float).
  showIndex?: boolean;
  // Added to each row's index — pass `page * pageSize` from the parent
  // so numbering stays continuous across paginated pages instead of
  // resetting to 1 on every page.
  indexOffset?: number;
  // Per-row class function. Mirrors AG Grid's getRowClass — returns a
  // CSS class (or null/undefined for none) given the row data. Used by
  // /raw-trades to mark the OPEN/HIGH/LOW/CLOSE-determining ticks in
  // green. Stacks with rowClassRules from columns; AG Grid concatenates
  // all class sources.
  getRowClass?: (row: TRow) => string | null | undefined;
  // Per-cell prefix injector. Returns optional JSX to prepend to a
  // specific (row, columnKey) cell. Used by /raw-trades to render an
  // "OPEN" badge inside the Price column on the row whose tick set the
  // candle open — same green/bold/check styling as the Orders Status
  // "Filled" badge (`greenWhenValue` in ColumnDef). When the function
  // returns null/undefined the cell renders normally.
  getCellPrefix?: (row: TRow, columnKey: string) => ReactNode | null | undefined;
}) {
  const { theme } = useTheme();
  const gridTheme = theme === "dark" ? darkTheme : lightTheme;
  const gridRef = useRef<AgGridReact>(null);

  // AG Grid only evaluates getRowClass at row creation. When the
  // function reference changes (e.g. /raw-trades's OHLC rules arrive
  // from /api/raw-trades/ohlc-rules after the initial render), we need
  // to explicitly redraw rows so the new classes apply. Using the
  // function's identity as the dependency is fine here because the
  // parent recreates it whenever the underlying data it closes over
  // changes — that's exactly when we want to re-tint rows.
  useEffect(() => {
    gridRef.current?.api?.redrawRows();
  }, [getRowClass, getCellPrefix, rows]);

  const colDefs = useMemo<ColDef[]>(() => {
    const dataCols: ColDef[] = columns.map((c) => {
      const fmt = formatterFor(c);
      const isNumeric = c.type === "decimal" || c.type === "number" || c.type === "number_abbreviated";

      // Enable click-header sort + per-column floating filter. Two
      // categories of column don't get a filter:
      //   - `computed` (client-side virtual)  — DB doesn't know it
      //   - `dbExpression` (server-side alias) — MySQL aliases work in
      //     ORDER BY but NOT in WHERE; sort still works, filter cannot.
      const filterType = (c.computed || c.dbExpression)
        ? false
        : (isNumericLike(c.type) ? "agNumberColumnFilter" : "agTextColumnFilter");

      const base: ColDef = {
        headerName: c.label,
        // Native browser tooltip on the column header — appears after
        // a short hover. Lets us document each column's meaning
        // without cluttering the grid surface.
        headerTooltip: c.tooltip,
        width: c.width,
        sortable: !c.computed,
        filter: filterType,
        floatingFilter: !!filterType,
        suppressHeaderMenuButton: true,   // hide the 3-dot menu, only floating
        valueFormatter: ({ value }) => fmt(value as unknown),
        cellClass: isNumeric ? "tabular-nums text-right" : "",
        headerClass: isNumeric ? "ag-right-aligned-header" : "",
      };

      // Computed (virtual) column: derive value from the row, no `field`.
      if (c.computed) {
        base.valueGetter = (params) =>
          c.computed!((params.data ?? {}) as Record<string, unknown>);
      } else {
        base.field = c.key;
      }

      // greenWhenValue — used by the Orders Status column. When
      // the formatted cell text equals the configured string (e.g.
      // "Filled"), render in green + bold with a check icon. Other
      // values render unchanged.
      if (c.greenWhenValue) {
        const target = c.greenWhenValue;
        base.cellRenderer = (p: { value: unknown; valueFormatted?: string | null }) => {
          const text = p.valueFormatted ?? (p.value == null ? "" : String(p.value));
          if (text === target) {
            return (
              <span className="inline-flex items-center gap-1.5 font-bold text-emerald-600 dark:text-emerald-400">
                {text}
                <CheckCircle2 className="size-3.5 shrink-0" />
              </span>
            );
          }
          return text;
        };
      }

      // formatAsMsForStatuses — used by the Orders Duration column.
      // When the row's `status` is in the configured list (e.g.
      // "Filled" or "Not executed", both written by ib_executor
      // after the TWS round-trip), render the (microsecond) value
      // as milliseconds with a " ms" suffix AND skip the
      // highlightAbove warning. The IB round-trip (~100–500 ms) is
      // inherent to TWS, not a C++ pipeline issue.
      if (c.formatAsMsForStatuses && c.formatAsMsForStatuses.length > 0) {
        const threshold = c.highlightAbove ?? Infinity;
        const msStatuses = new Set(c.formatAsMsForStatuses);
        base.cellRenderer = (p: { value: unknown; valueFormatted?: string | null; data?: { status?: unknown } }) => {
          const num = Number(p.value);
          const text = p.valueFormatted ?? (p.value == null ? "" : String(p.value));
          const status = p.data?.status;
          const isMs = typeof status === "string" && msStatuses.has(status);
          if (isMs && Number.isFinite(num)) {
            const ms = num / 1000;
            return (
              <span className="text-zinc-700 dark:text-zinc-300">
                {ms.toLocaleString("en-US", { maximumFractionDigits: 1, minimumFractionDigits: 1 })} ms
              </span>
            );
          }
          if (Number.isFinite(num) && num > threshold) {
            return (
              <span className="inline-flex items-center justify-end gap-1.5 w-full font-semibold text-amber-700 dark:text-amber-400">
                <AlertTriangle className="size-3.5 shrink-0" />
                {text}
              </span>
            );
          }
          return text;
        };
      }

      // Fill-check decoration — used by the Signals table's
      // purchasePrediction column. When the row's `was_filled` field
      // is true and the cell value is "BUY", we append a small green
      // check icon. Other values render unchanged.
      if (c.showFillCheck) {
        base.cellRenderer = (p: { value: unknown; valueFormatted?: string | null; data?: { was_filled?: boolean } }) => {
          const text = p.valueFormatted ?? (p.value == null ? "" : String(p.value));
          const filled = !!p.data?.was_filled;
          if (filled && text === "BUY") {
            return (
              <span className="inline-flex items-center gap-1.5 font-bold text-emerald-600 dark:text-emerald-400">
                {text}
                <CheckCircle2 className="size-3.5 shrink-0" />
              </span>
            );
          }
          return text;
        };
      }

      // Trend indicator vs another row column. When the cell's numeric
      // value differs from row[trendVsKey], append a colored arrow:
      //   value > ref → green up-arrow (in profit)
      //   value < ref → red down-arrow (in drawdown)
      //   equal or either side null → no icon
      // Used by the Portfolio's `last_price` vs `avg_cost`. The
      // refresh cycle is driven by the existing 5-second poll on
      // /api/portfolio — every refetch re-evaluates the comparison
      // and the icon flips automatically.
      if (c.trendVsKey) {
        const refKey = c.trendVsKey;
        base.cellRenderer = (p: { value: unknown; valueFormatted?: string | null; data?: Record<string, unknown> }) => {
          const num  = Number(p.value);
          const ref  = Number(p.data?.[refKey]);
          const text = p.valueFormatted ?? (p.value == null ? "" : String(p.value));
          if (!Number.isFinite(num) || !Number.isFinite(ref) || num === ref) {
            return text;
          }
          const up = num > ref;
          const Icon = up ? TrendingUp : TrendingDown;
          const colorClass = up
            ? "text-emerald-600 dark:text-emerald-400"
            : "text-red-600 dark:text-red-500";
          return (
            <span className={`inline-flex items-center justify-end gap-1.5 w-full font-semibold ${colorClass}`}>
              {text}
              <Icon className="size-3.5 shrink-0" />
            </span>
          );
        };
      }

      // Sign-colored percentage cell. Renders the numeric value as
      // "+X.XX%" (emerald) when positive, "-X.XX%" (red) when
      // negative, "0.00%" muted when zero. Blank when null / NaN.
      if (c.pctColored) {
        base.cellRenderer = (p: { value: unknown }) => {
          const num = Number(p.value);
          if (!Number.isFinite(num)) return "";
          const sign = num > 0 ? "+" : "";
          const text = `${sign}${num.toFixed(2)}%`;
          const colorClass =
            num > 0
              ? "text-emerald-600 dark:text-emerald-400"
              : num < 0
                ? "text-red-600 dark:text-red-500"
                : "text-zinc-500 dark:text-zinc-400";
          return <span className={`font-semibold ${colorClass}`}>{text}</span>;
        };
      }

      // Threshold-based cell decoration. Three severity levels:
      //   warning → amber triangle, row tinted (handled by rowClassRules)
      //   danger  → red octagon-stop, cell only (NOT a soft warning;
      //             different icon shape so the meaning is unambiguous)
      //   success → emerald check, cell only (positive flag — e.g.
      //             squeeze candidates on the Low Float page)
      // Skipped when `formatAsMsForStatuses` is set — that renderer
      // already implements the warning fall-through for rows that
      // don't match the ms list.
      if (typeof c.highlightAbove === "number" && !c.formatAsMsForStatuses) {
        const threshold = c.highlightAbove;
        const severity = c.highlightSeverity ?? "warning";
        const colorClass =
          severity === "danger"
            ? "text-red-600 dark:text-red-500"
            : severity === "success"
              ? "text-emerald-600 dark:text-emerald-400"
              : "text-amber-700 dark:text-amber-400";
        const Icon =
          severity === "danger"
            ? OctagonAlert
            : severity === "success"
              ? CheckCircle2
              : AlertTriangle;
        base.cellRenderer = (p: { value: unknown; valueFormatted?: string | null }) => {
          const num = Number(p.value);
          const text = p.valueFormatted ?? (p.value == null ? "" : String(p.value));
          if (Number.isFinite(num) && num > threshold) {
            return (
              <span className={`inline-flex items-center justify-end gap-1.5 w-full font-semibold ${colorClass}`}>
                <Icon className="size-4 shrink-0" />
                {text}
              </span>
            );
          }
          return text;
        };
      }

      // Per-cell prefix injection. Wraps the cellRenderer (or installs
      // one if none was set above) so the page can prepend a JSX badge
      // to specific (row, columnKey) cells. Used by /raw-trades for
      // the OPEN badge on the candle-open row's Price cell.
      if (getCellPrefix) {
        const prevRenderer = base.cellRenderer as
          | ((p: { value: unknown; valueFormatted?: string | null; data?: TRow }) => ReactNode)
          | undefined;
        base.cellRenderer = (p: { value: unknown; valueFormatted?: string | null; data?: TRow }) => {
          const prefix = p.data ? getCellPrefix(p.data, c.key) : null;
          const inner = prevRenderer
            ? prevRenderer(p)
            : (p.valueFormatted ?? (p.value == null ? "" : String(p.value)));
          if (!prefix) return inner;
          return (
            <span className="inline-flex items-center justify-end gap-2 w-full">
              {prefix}
              <span>{inner}</span>
            </span>
          );
        };
      }

      return base;
    });

    let result = dataCols;

    // Optional leading "#" column. Pinned left so it stays visible
    // when the user scrolls the data columns horizontally.
    if (showIndex) {
      const indexCol: ColDef = {
        headerName: "#",
        width: 60,
        pinned: "left",
        sortable: false,
        filter: false,
        resizable: false,
        suppressHeaderMenuButton: true,
        cellClass: "tabular-nums text-right text-zinc-500 dark:text-zinc-500",
        valueGetter: (params) => (params.node?.rowIndex ?? 0) + indexOffset + 1,
      };
      result = [indexCol, ...result];
    }

    if (rowAction) {
      const actionCol: ColDef = {
        headerName: "",
        width: rowAction.width ?? 60,
        pinned: "right",
        sortable: false,
        filter: false,
        resizable: false,
        cellStyle: { display: "flex", alignItems: "center", justifyContent: "center", padding: 0 },
        cellRenderer: (p: { data: TRow }) => rowAction.render(p.data),
      };
      result = [...result, actionCol];
    }

    return result;
    // getCellPrefix MUST be in the deps — when /raw-trades's OHLC
    // rules arrive async and the parent rebuilds the function, the
    // cellRenderer closure has to capture the new function, not the
    // initial-render `undefined` that produced no badge.
  }, [columns, rowAction, showIndex, indexOffset, getCellPrefix]);

  // Build rowClassRules from columns that opt into row-level highlighting.
  // Three sources stack into the same rules map:
  //   1. `highlightAbove` (warning severity) → row-warning class
  //   2. `rowClassWhenSet` → arbitrary class when the column has a
  //      non-null / non-empty value on the row (e.g. row-sold for
  //      Portfolio rows with sold_at populated)
  //   "danger" severity is intentionally excluded — those get a red
  //   cell icon only so a few outliers don't flood the whole table.
  const rowClassRules = useMemo(() => {
    const rules: Record<string, (params: RowClassParams) => boolean> = {};

    // (1) numeric > threshold triggers — only "warning" severity
    // tints the whole row. "danger" and "success" decorate the cell
    // only so the table doesn't flood when many rows match.
    const numericTriggers = columns.filter(
      (c) => typeof c.highlightAbove === "number"
              && c.highlightSeverity !== "danger"
              && c.highlightSeverity !== "success"
    );
    if (numericTriggers.length > 0) {
      rules["row-warning"] = (params) => {
        const data = params.data as Record<string, unknown> | undefined;
        if (!data) return false;
        for (const c of numericTriggers) {
          if (c.formatAsMsForStatuses
              && typeof data.status === "string"
              && c.formatAsMsForStatuses.includes(data.status)) {
            continue;
          }
          const raw = c.computed ? c.computed(data) : data[c.key];
          const num = Number(raw);
          if (Number.isFinite(num) && num > (c.highlightAbove as number)) {
            return true;
          }
        }
        return false;
      };
    }

    // (2) presence-of-value triggers — group by class name so multiple
    //     columns can share the same row class.
    const byClass = new Map<string, ColumnDef[]>();
    for (const c of columns) {
      if (!c.rowClassWhenSet) continue;
      const arr = byClass.get(c.rowClassWhenSet) ?? [];
      arr.push(c);
      byClass.set(c.rowClassWhenSet, arr);
    }
    for (const [className, cols] of byClass) {
      rules[className] = (params) => {
        const data = params.data as Record<string, unknown> | undefined;
        if (!data) return false;
        for (const c of cols) {
          const v = data[c.key];
          if (v !== null && v !== undefined && v !== "") return true;
        }
        return false;
      };
    }

    // (3) prefix-match triggers — used by the Portfolio's sold_reason
    //     column to split STOP_LOSS (orange) from TAKE_PROFIT (green).
    //     Group by class name so multiple prefixes can route to the
    //     same class if needed.
    const byPrefixClass = new Map<string, { col: ColumnDef; prefix: string }[]>();
    for (const c of columns) {
      if (!c.rowClassByPrefix) continue;
      for (const rule of c.rowClassByPrefix) {
        const arr = byPrefixClass.get(rule.className) ?? [];
        arr.push({ col: c, prefix: rule.prefix });
        byPrefixClass.set(rule.className, arr);
      }
    }
    for (const [className, entries] of byPrefixClass) {
      rules[className] = (params) => {
        const data = params.data as Record<string, unknown> | undefined;
        if (!data) return false;
        for (const { col, prefix } of entries) {
          const v = data[col.key];
          if (typeof v === "string" && v.startsWith(prefix)) return true;
        }
        return false;
      };
    }

    return Object.keys(rules).length > 0 ? rules : undefined;
  }, [columns]);

  return (
    <div className="h-full w-full">
      <AgGridReact
        ref={gridRef}
        theme={gridTheme}
        rowData={rows as object[]}
        columnDefs={colDefs}
        rowClassRules={rowClassRules}
        getRowClass={
          getRowClass
            ? (params) => {
                const cls = getRowClass(params.data as TRow);
                return cls ?? undefined;
              }
            : undefined
        }
        rowHeight={32}
        headerHeight={36}
        floatingFiltersHeight={32}
        suppressCellFocus
        animateRows={false}
        rowSelection="single"
        onSortChanged={(event: SortChangedEvent) => {
          if (!onSortChange) return;
          const sorted = event.api
            .getColumnState()
            .filter((s) => s.sort)
            .sort(
              (a, b) => (a.sortIndex ?? 0) - (b.sortIndex ?? 0)
            );
          if (sorted.length === 0) {
            onSortChange(undefined);
          } else {
            const first = sorted[0];
            onSortChange({
              column: first.colId as string,
              dir: first.sort as SortDir,
            });
          }
        }}
        onFilterChanged={(event: FilterChangedEvent) => {
          if (!onFilterChange) return;
          const model = event.api.getFilterModel() as Record<
            string,
            { filterType?: string; type?: string; filter?: unknown }
          >;
          const filters: Filter[] = [];
          for (const [column, m] of Object.entries(model)) {
            if (!m || m.filter == null || m.filter === "") continue;
            const opMap =
              m.filterType === "number" ? NUMBER_OP_MAP : TEXT_OP_MAP;
            const op = m.type ? opMap[m.type] : undefined;
            if (!op) continue;
            const value =
              m.filterType === "number" ? Number(m.filter) : String(m.filter);
            if (m.filterType === "number" && !Number.isFinite(value as number))
              continue;
            filters.push({ column, op, value: value as string | number });
          }
          onFilterChange(filters);
        }}
      />
    </div>
  );
}
