"use client";

import Link from "next/link";
import { useState } from "react";
import { LineChart, BarChart3, CheckCircle2 } from "lucide-react";
import { useQuery, keepPreviousData } from "@tanstack/react-query";
import { TablePage } from "@/components/TablePage";
import { DataGrid } from "@/components/DataGrid";
import { Pagination } from "@/components/Pagination";
import { DownloadTradesDialog } from "@/components/DownloadTradesDialog";
import { RAW_TRADES_COLUMNS, RAW_QUOTES_COLUMNS } from "@/lib/tables";
import type { Filter, SortDir } from "@/lib/query-builder";

type RawTradeRow = {
  id: number | null;
  symbol: string | null;
  close: number | string | null;
  volume: number | null;
  timestamp: string | null;
  second: string | null;
  transactions: number | null;
  exchange: string | null;
  trade_id: string | null;
  trf_id: string | null;
  conditions: string | null;
};

function ToolbarActions() {
  return (
    <div className="flex items-center gap-2">
      <DownloadTradesDialog apiPath="/api/raw-trades/run" />
      <Link
        href="/raw-trades/chart"
        className="inline-flex items-center gap-2 px-4 h-9 rounded-xl bg-zinc-900/[0.04] dark:bg-white/[0.04] border border-zinc-900/10 dark:border-white/10 text-sm font-semibold text-zinc-900 dark:text-zinc-100 transition-all duration-300 hover:bg-amber-500/10 hover:border-amber-500/30 hover:text-amber-700 dark:hover:text-amber-300 active:scale-[0.97]"
      >
        <LineChart className="size-4 text-amber-600 dark:text-amber-400" />
        View chart
      </Link>
    </div>
  );
}

export default function RawTradesPage() {
  // OHLC rules — fetched once and reused for both side-panel summary
  // and getRowClass row tinting. See computeOhlc() below for the C++
  // logic this replicates (trade_processor.h:580-886).
  const { data: rules } = useQuery<OhlcRules>({
    queryKey: ["/api/raw-trades/ohlc-rules"],
    queryFn: async () => {
      const r = await fetch("/api/raw-trades/ohlc-rules");
      if (!r.ok) throw new Error(`fetch ohlc-rules failed (${r.status})`);
      return r.json();
    },
    staleTime: 5 * 60_000,   // CSV + config change rarely
  });

  return (
    <TablePage<RawTradeRow>
      title="Raw Tape — Trades & Quotes downloader"
      description="RawTrades + RawQuotes"
      apiPath="/api/raw-trades"
      columns={RAW_TRADES_COLUMNS}
      clearEndpoint="/api/raw-trades/clear"
      toolbarExtra={<ToolbarActions />}
      showPageSizeSelector
      renderSidePanel={(rows) => <SummaryPanel rows={rows} rules={rules} />}
      getRowClass={(row, allRows) => {
        if (!rules) return null;
        const ohlc = rows__ohlc__cache(allRows, rules).result;
        if (!ohlc || row.id == null) return null;
        if (ohlc.openId  === row.id) return "row-ohlc";
        if (ohlc.closeId === row.id) return "row-ohlc";
        if (ohlc.highIds.has(row.id)) return "row-ohlc";
        if (ohlc.lowIds.has(row.id))  return "row-ohlc";
        return null;
      }}
      getCellPrefix={(row, allRows, columnKey) => {
        if (!rules || row.id == null) return null;
        const ohlc = rows__ohlc__cache(allRows, rules).result;
        if (!ohlc) return null;

        // OPEN badge inside the Price cell of the row whose tick
        // set the candle's open. Same green/bold/check styling as
        // the Orders Status "Filled" badge.
        if (columnKey === "close") {
          if (ohlc.openId !== row.id) return null;
          return (
            <span className="inline-flex items-center gap-1 font-bold text-emerald-600 dark:text-emerald-400">
              OPEN
              <CheckCircle2 className="size-3.5 shrink-0" />
            </span>
          );
        }

        // Low activity badge in the Activity column. Mirrors the
        // C++ passes_activity_check that demotes BUY signals to
        // LOW_ACTIVITY when active_seconds ≤ elapsed × threshold.
        if (columnKey === "_activity_status") {
          if (!ohlc.lowActivityIds.has(row.id)) return null;
          return (
            <span className="inline-flex items-center font-semibold text-amber-600 dark:text-amber-400 text-xs">
              Low activity
            </span>
          );
        }

        return null;
      }}
      bottomPanel={<QuotesSection />}
    />
  );
}

// ── Quotes section — second grid below the trades grid ──────────
//
// Renders the RawQuotes table for the same minute the operator
// downloaded. Independent state from the trades grid: own filters,
// own sort, own pagination. Polls /api/raw-quotes every 5 s like
// every other table on the dashboard.
//
// Layout intentionally mirrors the trades grid (same height, same
// glass-card look) so the operator can scan trades on top + quotes
// below with the same visual rhythm.
type RawQuoteRow = {
  id: number | null;
  symbol: string | null;
  bid_price: number | string | null;
  bid_size: number | null;
  ask_price: number | string | null;
  ask_size: number | null;
  spread: number | string | null;
  timestamp: string | null;
};

type ApiResponse<T> = { rows: T[]; total: number };

function QuotesSection() {
  const [page, setPage] = useState(0);
  const [pageSize, setPageSize] = useState(100);
  const [filters, setFilters] = useState<Filter[]>([]);
  const [sort, setSort] = useState<{ column: string; dir: SortDir } | undefined>(undefined);

  const { data, isFetching, error } = useQuery<ApiResponse<RawQuoteRow>>({
    queryKey: ["/api/raw-quotes", page, pageSize, filters, sort],
    queryFn: async () => {
      const params = new URLSearchParams({
        page: String(page),
        pageSize: String(pageSize),
      });
      if (filters.length > 0) params.set("filters", JSON.stringify(filters));
      if (sort)               params.set("sort",    JSON.stringify(sort));
      const r = await fetch(`/api/raw-quotes?${params.toString()}`);
      if (!r.ok) throw new Error(`fetch /api/raw-quotes failed (${r.status})`);
      return r.json();
    },
    refetchInterval: 5_000,
    placeholderData: keepPreviousData,
  });

  const rows = data?.rows ?? [];
  const total = data?.total ?? 0;

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-end justify-between">
        <div>
          <div className="text-[11px] uppercase tracking-[0.22em] text-zinc-500">
            RawQuotes
          </div>
          <h2 className="mt-2 text-2xl font-bold tracking-tight text-zinc-900 dark:text-white">
            NBBO Quotes — bid/ask snapshots
          </h2>
          <div className="mt-3 h-0.5 w-12 rounded-full bg-gradient-to-r from-amber-400 to-orange-500" />
        </div>
        <div className="flex items-center gap-3">
          <Link
            href="/raw-trades/spread-chart"
            className="inline-flex items-center gap-2 px-4 h-9 rounded-xl bg-zinc-900/[0.04] dark:bg-white/[0.04] border border-zinc-900/10 dark:border-white/10 text-sm font-semibold text-zinc-900 dark:text-zinc-100 transition-all duration-300 hover:bg-amber-500/10 hover:border-amber-500/30 hover:text-amber-700 dark:hover:text-amber-300 active:scale-[0.97]"
          >
            <LineChart className="size-4 text-amber-600 dark:text-amber-400" />
            View spread chart
          </Link>
          <div className="text-xs text-zinc-500 dark:text-zinc-400 tabular-nums">
            {isFetching ? "fetching…" : `${total.toLocaleString()} rows`}
          </div>
        </div>
      </div>

      {error ? (
        <div className="rounded-xl bg-red-500/10 border border-red-500/20 px-4 py-3 text-sm text-red-600 dark:text-red-400">
          Error: {(error as Error).message}
        </div>
      ) : (
        <div className="grid grid-cols-1 xl:grid-cols-[1fr_320px] gap-5">
          <div className="h-[40rem] rounded-2xl bg-zinc-900/[0.03] dark:bg-white/[0.03] border border-zinc-900/5 dark:border-white/5 overflow-hidden shadow-lg shadow-black/5 dark:shadow-black/20">
            <DataGrid<RawQuoteRow>
              rows={rows}
              columns={RAW_QUOTES_COLUMNS}
              onFilterChange={(next) => { setFilters(next); setPage(0); }}
              onSortChange={(next)   => { setSort(next);    setPage(0); }}
            />
          </div>
          <QuotesSummaryPanel rows={rows} total={total} filters={filters} />
        </div>
      )}

      <Pagination
        page={page}
        pageSize={pageSize}
        total={total}
        onPageChange={setPage}
        onPageSizeChange={(size) => { setPageSize(size); setPage(0); }}
      />
    </div>
  );
}


// ── Quotes summary panel ─────────────────────────────────────────
//
// Renders next to the Quotes grid (xl breakpoint) or below it (mobile).
// Worst / best / average spread are computed in SQL over the FULL
// filtered set via /api/raw-quotes/aggregate — not just the visible
// page. Reacts to the same filter state the grid uses, so narrowing
// by symbol updates both grid and panel together.
//
// Negative spreads (rare crossed-market quotes) are kept in the calc
// because they're real market events worth surfacing.
type QuotesAggregate = {
  worst: number | null;
  best:  number | null;
  avg:   number | null;
  count: number;
};

function QuotesSummaryPanel({
  rows,
  total,
  filters,
}: {
  rows: RawQuoteRow[];
  total: number;
  filters: Filter[];
}) {
  const symbol = rows[0]?.symbol ?? null;

  const { data: agg } = useQuery<QuotesAggregate>({
    queryKey: ["/api/raw-quotes/aggregate", filters],
    queryFn: async () => {
      const params = new URLSearchParams();
      if (filters.length > 0) params.set("filters", JSON.stringify(filters));
      const r = await fetch(`/api/raw-quotes/aggregate?${params.toString()}`);
      if (!r.ok) throw new Error(`fetch /api/raw-quotes/aggregate failed (${r.status})`);
      return r.json();
    },
    refetchInterval: 5_000,
    placeholderData: keepPreviousData,
  });

  const worst = agg?.worst ?? null;
  const best  = agg?.best  ?? null;
  const avg   = agg?.avg   ?? null;
  const count = agg?.count ?? 0;

  return (
    <div className="rounded-2xl bg-zinc-900/[0.03] dark:bg-white/[0.03] border border-zinc-900/5 dark:border-white/5 px-5 py-4 shadow-lg shadow-black/5 dark:shadow-black/20 self-start">
      <div className="flex items-center gap-3 pb-4 border-b border-zinc-900/5 dark:border-white/5">
        <div className="size-9 rounded-xl bg-amber-500/10 border border-amber-500/20 flex items-center justify-center shrink-0">
          <BarChart3 className="size-4 text-amber-600 dark:text-amber-400" />
        </div>
        <div>
          <div className="text-[10px] uppercase tracking-[0.22em] text-zinc-500">
            Quotes summary
          </div>
          <div className="font-bold text-lg text-zinc-900 dark:text-white">
            {symbol ?? "—"}
          </div>
        </div>
      </div>

      <dl className="mt-4 space-y-3 text-sm">
        <Row label="Worst spread (max)"  value={fmtSpread(worst)} />
        <Row label="Best spread (min)"   value={fmtSpread(best)}  />
        <Row label="Average spread"      value={fmtSpread(avg)}
             emphasize={avg !== null && avg > 0.10} />
      </dl>

      <div className="mt-4 pt-4 border-t border-zinc-900/5 dark:border-white/5 space-y-3 text-sm">
        <Row label="Quotes total"        value={(count || total).toLocaleString()} />
      </div>

      <div className="mt-4 text-[11px] text-zinc-500 dark:text-zinc-500 leading-relaxed">
        Stats computed in SQL across all {(count || total).toLocaleString()} quotes
        matching the active filters. Negative spreads (crossed market)
        are included; widening spreads precede market-maker retreat.
      </div>
    </div>
  );
}

function fmtSpread(n: number | null | undefined): string {
  if (n === null || n === undefined || !Number.isFinite(n)) return "—";
  return `$ ${n.toFixed(4)}`;
}

// ── OHLC computation — replicates trade_processor.h:580-886 ───────
//
// The C++ trader's per-minute candle is built by two gates:
//
//   condition_allows(trade, COMP) (trade_processor.h:580-589):
//     - num_conditions == 0  → allow (plain trade)
//     - else: ALL conditions must permit COMP. Any condition denying
//       blocks the entire trade for that component. Unknown ids → deny.
//
//   Block 0 — first trade of the minute (line 868):
//     - if (c.open == 0.0 && allow_oc):
//         set open, high, low, AND close to trade.price.
//         NO size check — the very first eligible tick wins, even
//         if its size is 1.
//     - return.
//
//   Block 1 — subsequent ticks (line 883):
//     - if (allow_hl && size >= min_trade_size):
//         close = trade.price       (last-eligible wins)
//         high  = max(high, price)
//         low   = min(low,  price)
//
// So OPEN is the FIRST tick passing the OC gate (any size).
// CLOSE is the LAST tick passing HL gate AND size ≥ min_trade_size.
// HIGH/LOW are max/min over the same eligible-for-HL set after OPEN.

type OhlcRules = {
  minTradeSize: number;
  // 2026-05-05 — added for the per-row "Low activity" badge column.
  // Mirrors C++ passes_activity_check: pass = active > elapsed * t.
  // Default 0.33 if the endpoint doesn't supply it (older binaries).
  lowActivityThreshold: number;
  conditions: Record<string, { oc: boolean; hl: boolean; vol: boolean }>;
};

type OhlcResult = {
  open:    number;
  close:   number;
  high:    number;
  low:     number;
  openId:  number;
  closeId: number;
  highIds: Set<number>;
  lowIds:  Set<number>;
  // 2026-05-05 — set of row ids that, at the moment they arrived, had
  // FEWER unique active seconds than `sec * lowActivityThreshold`.
  // Used by the Activity column in /raw-trades to render the "Low
  // activity" badge.
  lowActivityIds: Set<number>;
};

// Parse a comma-separated condition string ("12, 37" → [12, 37]).
// Empty / null / "[]" → empty array (plain trade).
function parseConditions(raw: string | null): number[] {
  if (!raw) return [];
  const t = raw.trim();
  if (!t || t === "[]") return [];
  return t
    .replace(/[[\]]/g, "")
    .split(",")
    .map((s) => Number(s.trim()))
    .filter((n) => Number.isFinite(n));
}

// Mirror of `condition_allows` in trade_processor.h:580.
function conditionAllows(
  conditions: number[],
  comp: "oc" | "hl" | "vol",
  rules: OhlcRules
): boolean {
  if (conditions.length === 0) return true;
  for (const cid of conditions) {
    const r = rules.conditions[String(cid)];
    if (!r) return false;          // unknown id → deny (matches line 585)
    if (!r[comp]) return false;    // any deny → entire trade blocked
  }
  return true;
}

// Memoise per-(rows, rules) so getRowClass doesn't re-compute on every
// AG Grid row callback. Keyed by reference — TanStack Query keeps the
// rows reference stable across renders unless data actually changed.
const ohlcCache = new WeakMap<
  RawTradeRow[],
  { rules: OhlcRules; result: OhlcResult | null }
>();

function rows__ohlc__cache(
  rows: RawTradeRow[],
  rules: OhlcRules
): { rows: RawTradeRow[]; result: OhlcResult | null } {
  const cached = ohlcCache.get(rows);
  if (cached && cached.rules === rules) {
    return { rows, result: cached.result };
  }
  const result = computeOhlcFromRows(rows, rules);
  ohlcCache.set(rows, { rules, result });
  return { rows, result };
}

function computeOhlcFromRows(
  rows: RawTradeRow[],
  rules: OhlcRules
): OhlcResult | null {
  if (rows.length === 0) return null;

  let openId:  number | null = null;
  let openPx:  number | null = null;
  let closeId: number | null = null;
  let closePx: number | null = null;
  let high: number = -Infinity;
  let low:  number = Infinity;
  const highIds = new Set<number>();
  const lowIds  = new Set<number>();

  // 2026-05-05 — per-row low-activity tracking.
  // Mirrors C++ trade_processor.h::passes_activity_check() (post the
  // 2026-05-05 fix that anchors elapsed at second 0 of the minute,
  // matching the Python original).
  //
  // Walk: as each VOL-eligible trade arrives (allow_vol && size ≥
  // min_trade_size), add its second-of-minute to `activeSeconds`.
  // Then for EVERY trade (eligible or not) compute:
  //
  //   elapsed   = trade's second_of_minute  (clamped to ≥1)
  //   threshold = elapsed × lowActivityThreshold
  //   active    = activeSeconds.size  (popcount equivalent)
  //   passes    = active > threshold
  //
  // If !passes → row id goes into lowActivityIds, which the Activity
  // column's getCellPrefix renders as a "Low activity" amber badge.
  const activeSeconds = new Set<number>();
  const lowActivityIds = new Set<number>();
  const threshold = rules.lowActivityThreshold;

  for (const row of rows) {
    const id    = row.id;
    const price = Number(row.close);
    const size  = Number(row.volume);
    if (id == null || !Number.isFinite(price)) continue;

    const conds   = parseConditions(row.conditions);
    const allowOc = conditionAllows(conds, "oc", rules);
    const allowHl = conditionAllows(conds, "hl", rules);
    const allowVol = conditionAllows(conds, "vol", rules);

    // VOL-eligible tick: register its second in the active set.
    // Same gate the C++ Block 2 uses (allow_vol + size ≥ min).
    const sec = (typeof row.second === "string")
      ? parseInt(row.second, 10) : NaN;
    if (allowVol && Number.isFinite(size) && size >= rules.minTradeSize
        && Number.isFinite(sec)) {
      activeSeconds.add(sec);
    }

    // Per-row activity check — uses elapsed = sec (clamped ≥1).
    if (Number.isFinite(sec)) {
      const elapsed = sec > 0 ? sec : 1;
      const passes = activeSeconds.size > elapsed * threshold;
      if (!passes) lowActivityIds.add(id);
    }

    // Block 0 — first eligible tick sets the OPEN (and seeds HLC).
    if (openId === null) {
      if (!allowOc) continue;
      openId  = id;
      openPx  = price;
      closeId = id;
      closePx = price;
      high = price;
      low  = price;
      highIds.clear(); highIds.add(id);
      lowIds.clear();  lowIds.add(id);
      continue;
    }

    // Block 1 — HL-eligible + size ≥ min_trade_size updates HLC.
    if (!allowHl) continue;
    if (!Number.isFinite(size) || size < rules.minTradeSize) continue;

    closeId = id;
    closePx = price;

    if (price > high) {
      high = price;
      highIds.clear();
      highIds.add(id);
    } else if (price === high) {
      highIds.add(id);
    }
    if (price < low) {
      low = price;
      lowIds.clear();
      lowIds.add(id);
    } else if (price === low) {
      lowIds.add(id);
    }
  }

  if (openId === null || openPx === null || closeId === null || closePx === null) {
    return null;
  }

  return {
    open:    openPx,
    close:   closePx,
    high,
    low,
    openId,
    closeId,
    highIds,
    lowIds,
    lowActivityIds,
  };
}

// ── Summary panel ──────────────────────────────────────────────────
//
// Shows the symbol of the loaded ticks plus an OHLC summary derived
// directly from the rows on screen (Open = first tick, Close = last
// tick, High/Low = min/max across rows). Pulls Shares Outstanding +
// Short % from /api/stocks for the same symbol — these come from the
// last `Float` pipeline run (Polygon SO + yfinance shortPercentOfFloat).
//
// The OHLC reflects whatever pageSize is selected. With "All" the
// values describe the entire downloaded session; with 100 they only
// cover the current page (clear in the panel header).

type StocksApiResponse = {
  rows: Array<{
    ticker: string | null;
    shares_outstanding: number | null;
    short_percent_float: number | string | null;
  }>;
  total: number;
};

type RvApiResponse = {
  rows: Array<{ relative_volume: number | null }>;
  total: number;
};

// Pull the first tick's hour out of the local-time ISO string the API
// returns ("2026-05-04T05:00:04.650571-06:00") and translate to the
// 12-hour + AM/PM form the RelativeVolumeRatioHour table indexes by.
//   00:xx → 12 AM   01-11:xx → 1-11 AM
//   12:xx → 12 PM   13-23:xx → 1-11 PM
function parseHourBucket(
  isoTimestamp: string | null | undefined,
): { hour: number; amPm: "AM" | "PM" } | null {
  if (!isoTimestamp) return null;
  const tIdx = isoTimestamp.indexOf("T");
  if (tIdx < 0) return null;
  const hh = parseInt(isoTimestamp.slice(tIdx + 1, tIdx + 3), 10);
  if (!Number.isFinite(hh) || hh < 0 || hh > 23) return null;
  const amPm: "AM" | "PM" = hh < 12 ? "AM" : "PM";
  const hour12 = ((hh % 12) === 0) ? 12 : (hh % 12);
  return { hour: hour12, amPm };
}

function SummaryPanel({
  rows,
  rules,
}: {
  rows: RawTradeRow[];
  rules: OhlcRules | undefined;
}) {
  // Derive Symbol from the first row. OHLC is computed using the same
  // gates the C++ trader uses (trade_processor.h:580-886), so the four
  // values shown here match what the candle would look like inside
  // process_trade — not a naive min/max over all ticks.
  const symbol = rows[0]?.symbol ?? null;
  const ohlc = rules
    ? rows__ohlc__cache(rows, rules).result
    : null;

  // Pull SO + Short % for this symbol from the master Stocks registry.
  // Single-row exact-match query — server-side filter, fast enough that
  // we don't bother caching outside React Query's defaults.
  const { data: stocks } = useQuery<StocksApiResponse>({
    queryKey: ["/api/stocks/symbol", symbol],
    enabled: !!symbol,
    queryFn: async () => {
      const params = new URLSearchParams({
        page: "0",
        pageSize: "1",
        filters: JSON.stringify([
          { column: "ticker", op: "eq", value: symbol },
        ]),
      });
      const r = await fetch(`/api/stocks?${params.toString()}`);
      if (!r.ok) throw new Error(`fetch /api/stocks failed (${r.status})`);
      return r.json();
    },
  });

  // Derive (hour, AM/PM) from the first tick on screen so we can look
  // up the RelativeVolumeRatioHour baseline for that exact bucket.
  // If the page filter chose ticks at 05:xx, this returns {5, AM}.
  const bucket = parseHourBucket(rows[0]?.timestamp);

  const { data: rv } = useQuery<RvApiResponse>({
    queryKey: ["/api/rv/lookup", symbol, bucket?.hour, bucket?.amPm],
    enabled: !!symbol && !!bucket,
    queryFn: async () => {
      const params = new URLSearchParams({
        page: "0",
        pageSize: "1",
        filters: JSON.stringify([
          { column: "symbol", op: "eq", value: symbol },
          { column: "hour",   op: "eq", value: bucket!.hour },
          { column: "amPm",   op: "eq", value: bucket!.amPm },
        ]),
      });
      const r = await fetch(`/api/rv?${params.toString()}`);
      if (!r.ok) throw new Error(`fetch /api/rv failed (${r.status})`);
      return r.json();
    },
  });

  const rvBaseline =
    typeof rv?.rows?.[0]?.relative_volume === "number"
      ? rv.rows[0].relative_volume
      : null;

  const stockRow = stocks?.rows?.[0];
  const sharesOutstanding =
    typeof stockRow?.shares_outstanding === "number"
      ? stockRow.shares_outstanding
      : null;
  // short_percent_float is stored as a 0..1 fraction (yfinance native
  // form). Multiply by 100 for the %-of-float display the user sees.
  const shortPctRaw =
    stockRow?.short_percent_float === null ||
    stockRow?.short_percent_float === undefined
      ? null
      : Number(stockRow.short_percent_float);
  const shortPct =
    shortPctRaw !== null && Number.isFinite(shortPctRaw)
      ? shortPctRaw * 100
      : null;

  return (
    <div className="rounded-2xl bg-zinc-900/[0.03] dark:bg-white/[0.03] border border-zinc-900/5 dark:border-white/5 p-5 shadow-lg shadow-black/5 dark:shadow-black/20 self-start">
      <div className="flex items-center gap-3 mb-4">
        <div className="size-9 rounded-xl bg-amber-500/10 border border-amber-500/20 flex items-center justify-center shrink-0">
          <BarChart3 className="size-4 text-amber-600 dark:text-amber-400" />
        </div>
        <div>
          <div className="text-[10px] uppercase tracking-[0.2em] text-zinc-500">
            Summary
          </div>
          <div className="text-sm font-semibold text-zinc-900 dark:text-white">
            {symbol ?? "No data loaded"}
          </div>
        </div>
      </div>

      <dl className="space-y-3 text-sm">
        <Row label="Open"  value={fmtPrice(ohlc?.open)}  />
        <Row label="High"  value={fmtPrice(ohlc?.high)}  />
        <Row label="Low"   value={fmtPrice(ohlc?.low)}   />
        <Row label="Close" value={fmtPrice(ohlc?.close)} />
      </dl>

      <div className="mt-4 pt-4 border-t border-zinc-900/5 dark:border-white/5 space-y-3 text-sm">
        <Row label="Shares Outstanding" value={fmtAbbrev(sharesOutstanding)} />
        <Row label="Short %"            value={fmtPct(shortPct)} />
        <Row
          label={
            bucket
              ? `RV Baseline (${bucket.hour} ${bucket.amPm})`
              : "RV Baseline"
          }
          value={fmtInt(rvBaseline)}
          emphasize
        />
        {/* Activity Threshold — surfaces the C++ low_activity_threshold
            (from trading_config.json, served by /api/raw-trades/
            ohlc-rules). Same value the Activity column uses to flag
            rows as "Low activity": at trade arrival, if
            active_seconds ≤ sec × threshold, the row is flagged.
            Helps the operator see exactly what % distribution the
            check was looking for when reading the Activity column. */}
        <Row
          label="Activity Threshold"
          value={
            rules
              ? `${(rules.lowActivityThreshold * 100).toFixed(0)} %`
              : "—"
          }
        />
      </div>

      <div className="mt-4 text-[11px] text-zinc-500 dark:text-zinc-500">
        Rows that determined OHLC are tinted <span className="text-emerald-600 dark:text-emerald-400 font-semibold">green</span>.
        OHLC computed from the {rows.length.toLocaleString()} ticks shown
        — switch rows-per-page to <span className="font-mono">All</span> for
        the full session.
      </div>

      <details className="mt-4 text-[11px] text-zinc-500 dark:text-zinc-500">
        <summary className="cursor-pointer hover:text-amber-600 dark:hover:text-amber-400 select-none">
          Selection rules (mirrors C++ trade_processor.h)
        </summary>
        <table className="w-full mt-3 text-[11px] border-collapse">
          <thead>
            <tr className="text-zinc-400 dark:text-zinc-500">
              <th className="text-left pb-1.5 font-medium">Field</th>
              <th className="text-left pb-1.5 font-medium">Rule</th>
            </tr>
          </thead>
          <tbody className="font-mono text-zinc-600 dark:text-zinc-400">
            <tr className="border-t border-zinc-900/5 dark:border-white/5">
              <td className="py-1.5 align-top text-emerald-600 dark:text-emerald-400 font-semibold">OPEN</td>
              <td className="py-1.5">FIRST tick · all conditions allow <code>updates_open_close</code> · any size</td>
            </tr>
            <tr className="border-t border-zinc-900/5 dark:border-white/5">
              <td className="py-1.5 align-top text-emerald-600 dark:text-emerald-400 font-semibold">HIGH</td>
              <td className="py-1.5">MAX price · all conditions allow <code>updates_high_low</code> · size ≥ {rules?.minTradeSize ?? 100}</td>
            </tr>
            <tr className="border-t border-zinc-900/5 dark:border-white/5">
              <td className="py-1.5 align-top text-emerald-600 dark:text-emerald-400 font-semibold">LOW</td>
              <td className="py-1.5">MIN price · same gate as HIGH</td>
            </tr>
            <tr className="border-t border-zinc-900/5 dark:border-white/5">
              <td className="py-1.5 align-top text-emerald-600 dark:text-emerald-400 font-semibold">CLOSE</td>
              <td className="py-1.5">LAST tick that passed the HIGH/LOW gate</td>
            </tr>
          </tbody>
        </table>
        <div className="mt-2 leading-relaxed">
          Conditions are AND-gated: a tick is eligible for a component
          only if <span className="italic">every</span> condition code on
          it permits that component (per <span className="font-mono">polygon_conditions_trade_stocks.csv</span>).
          Plain ticks (no conditions) are always eligible.
        </div>
      </details>
    </div>
  );
}

function Row({
  label,
  value,
  emphasize = false,
}: {
  label: string;
  value: string;
  emphasize?: boolean;
}) {
  // emphasize=true → label bold (dark text) and value bold + red.
  // Used to highlight the RV Baseline row against the rest of the
  // summary so the operator sees the baseline figure at a glance.
  const labelClass = emphasize
    ? "font-semibold text-zinc-900 dark:text-zinc-100"
    : "text-zinc-500 dark:text-zinc-400";
  const valueClass = emphasize
    ? "font-mono tabular-nums font-semibold text-red-600 dark:text-red-400"
    : "font-mono tabular-nums text-zinc-900 dark:text-zinc-100";
  return (
    <div className="flex items-baseline justify-between gap-3">
      <dt className={labelClass}>{label}</dt>
      <dd className={valueClass}>{value}</dd>
    </div>
  );
}

function fmtPrice(n: number | undefined): string {
  if (n === undefined || !Number.isFinite(n)) return "—";
  return `$ ${n.toFixed(4)}`;
}

function fmtAbbrev(n: number | null): string {
  if (n === null || !Number.isFinite(n)) return "—";
  if (n >= 1_000_000_000) return `${(n / 1_000_000_000).toFixed(2)} B`;
  if (n >= 1_000_000)     return `${(n / 1_000_000).toFixed(2)} M`;
  if (n >= 1_000)         return `${(n / 1_000).toFixed(2)} K`;
  return n.toLocaleString();
}

function fmtPct(n: number | null): string {
  if (n === null || !Number.isFinite(n)) return "—";
  return `${n.toFixed(2)} %`;
}

function fmtInt(n: number | null): string {
  if (n === null || !Number.isFinite(n)) return "—";
  return n.toLocaleString("en-US");
}
