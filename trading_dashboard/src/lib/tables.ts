// Per-table metadata: column whitelist (for SQL safety) and the
// columns we actually surface in the dashboard.

export type ColumnDef = {
  key: string;
  label: string;
  type: "text" | "number" | "number_abbreviated" | "decimal" | "datetime_ms" | "datetime_double_seconds" | "datetime_decimal_seconds" | "iso_local_timestamp" | "iso_local_date" | "iso_local_time" | "local_time_ms" | "local_time_double_seconds" | "local_time_decimal_seconds";
  width?: number;
  // For "decimal" type: how many fractional digits to render (default 4).
  decimals?: number;
  // String appended to the formatted value (after `decimals` rounding,
  // before any cell-level decoration like the highlight icon). Use for
  // unit suffixes — e.g. "%" on the Low Float page's Short %, or " ms"
  // on a latency column. Empty values stay empty (suffix not appended).
  suffix?: string;
  // String prepended to the formatted value. Mirror of `suffix` for
  // currency / unit prefixes — e.g. "$ " on the Low Float page's
  // Last Close. Empty values stay empty (prefix not prepended).
  prefix?: string;
  // Virtual column — value is derived from a row at render time, not
  // selected from the database. Excluded from SQL projection / sort /
  // filter. Useful for columns like "duration = end - start".
  computed?: (row: Record<string, unknown>) => number | string | null;
  // When set together with `computed` (or a numeric DB column), AG Grid
  // adds a row-level warning class if the cell value exceeds this
  // threshold. Used for "Duration > 10 µs → highlight orange".
  highlightAbove?: number;
  // Severity of the threshold:
  //   "warning" (default)  amber icon + text · row tinted amber
  //   "danger"             red icon + text · row NOT tinted
  //                        (for hard outliers like "Latency > 2 s")
  //   "success"            emerald check + text · row NOT tinted
  //                        (for positive flags like "Short % > 10" —
  //                        squeeze candidates on the Low Float page)
  // Both "danger" and "success" skip the row tint so the table
  // doesn't flood when many rows match.
  highlightSeverity?: "warning" | "danger" | "success";
  // Native browser tooltip shown when the user hovers the column
  // header. One-sentence explanation of what the value means and
  // where it comes from.
  tooltip?: string;
  // When true, AG Grid adds a small green check-circle icon next to
  // the cell value if the row's `was_filled` field is true. Used by
  // the Signals table's `purchasePrediction` column so the operator
  // sees at a glance which BUY signals actually executed (= produced
  // an Orders row with status='Filled'). Other values of the column
  // are unchanged.
  showFillCheck?: boolean;
  // Render the cell green + bold + check-circle icon whenever the
  // formatted value equals this string. Used by the Orders Status
  // column to make "Filled" rows pop. Other status values are
  // rendered unchanged.
  greenWhenValue?: string;
  // For numeric duration-like columns (microseconds): when the
  // row's `status` field is one of these strings, reformat the
  // value as milliseconds (divide by 1000, append " ms") AND
  // suppress the highlightAbove warning icon. Reasoning: any row
  // written by ib_executor (status ∈ {"Filled", "Not executed"})
  // has a duration that includes the TWS round-trip — tens to
  // hundreds of ms is normal, not a sign of trouble in the C++
  // pipeline. Only "Processing" rows (pure C++ cost) keep the
  // microsecond view + > 10 µs warning.
  formatAsMsForStatuses?: string[];
  // When this column has a non-null / non-empty value on a row,
  // apply this CSS class to the WHOLE row. Used by the Portfolio
  // page so positions that have been sold during the session keep
  // showing up but get tinted (orange) so the operator instantly
  // sees "this is no longer mine". The class string must exist in
  // globals.css (`row-sold` is defined alongside `row-warning`).
  rowClassWhenSet?: string;
  // Value-driven row tint. Each entry: when the cell value STARTS
  // WITH the given prefix, apply `className` to the whole row.
  // Used by the Portfolio page's `sold_reason` column so STOP_LOSS
  // rows go orange (warning) and TAKE_PROFIT rows go green
  // (success), instead of one neutral "sold" tint for both.
  // First match wins. Prefix match (not full equality) because the
  // reason string carries extra context, e.g.
  //   "STOP_LOSS @ -8.87% (cost=1.2400 tick=1.1300)"
  rowClassByPrefix?: { prefix: string; className: string }[];
  // Numeric trend indicator. When set, the cell compares its own
  // numeric value against the row's value at this key and appends a
  // small arrow icon: green up-arrow when this > ref, red down-arrow
  // when this < ref, no icon when equal or either side is missing.
  // Used by the Portfolio page's `last_price` column to show, at a
  // glance, whether each holding is above or below its `avg_cost` —
  // i.e. the live P&L direction.
  trendVsKey?: string;
  // Server-side computed column. SQL fragment that produces the value
  // for this column at SELECT time, instead of reading a DB field with
  // the same name. The handler emits `(expression) AS \`key\`` in the
  // projection. The column is still SORTABLE (MySQL accepts aliases in
  // ORDER BY) but NOT FILTERABLE (aliases don't work in WHERE — the
  // DataGrid auto-disables the floating filter when this is set).
  // Used by the Low Float page's `Short %` column to compute
  // shares_short / shares_outstanding × 100 directly in SQL so the
  // server-side sort works on the live ratio rather than the stale
  // yfinance `short_percent_float` value.
  dbExpression?: string;
  // When true, render the cell as a signed percentage with sign
  // coloring:
  //   value > 0   → "+5.00%" in emerald
  //   value < 0   → "-5.00%" in red
  //   value == 0  → "0.00%"   in muted text
  //   null / NaN  → blank cell
  // Used by the Portfolio page's `pnl_pct` column to surface live
  // P&L %, paired visually with the Last column.
  pctColored?: boolean;
};

// Returns the keys that actually exist as DB columns — i.e. the keys
// whose ColumnDef is NOT marked `computed`. Use to build SELECT
// projections and sort/filter whitelists.
//
// Columns with `dbExpression` ARE included — they're computed server
// side via a SQL expression but still appear as a real (aliased)
// column in the result set, sortable via the alias.
export function dbColumnKeys(cols: ColumnDef[]): string[] {
  return cols.filter((c) => !c.computed).map((c) => c.key);
}

// Map of `key -> SQL expression` for columns that opt into server-side
// computation via `dbExpression`. The handler uses this to emit
// `(expression) AS \`key\`` in the SELECT projection. Other columns
// fall back to a plain backticked column reference.
export function dbExpressionMap(cols: ColumnDef[]): Record<string, string> {
  const map: Record<string, string> = {};
  for (const c of cols) {
    if (c.dbExpression) map[c.key] = c.dbExpression;
  }
  return map;
}

// ── TradeSignalsBuyPerSecond ─────────────────────────────────────

export const SIGNALS_TABLE = "TradeSignalsBuyPerSecond";

export const SIGNALS_COLUMNS: ColumnDef[] = [
  { key: "symbol",             label: "Symbol",      type: "text",    width: 90,
    tooltip: "Stock ticker for the symbol that fired this signal." },
  { key: "timestamp_unix",     label: "Trade Time",   type: "local_time_ms",             width: 130,
    tooltip: "Polygon SIP timestamp — exact moment the trade occurred at the exchange (millisecond precision)." },
  { key: "timestamp",          label: "Local Time",   type: "local_time_double_seconds", width: 130,
    tooltip: "Wall clock when our C++ processor pushed this signal to the persist ring (microsecond precision)." },
  { key: "local_utc_timestamp", label: "Latency (ms)", type: "number",                   width: 120,
    tooltip: "Transport latency: arrival time on our box minus the Polygon SIP timestamp. Pure network + Polygon-internal delay. > 2000 ms flags as danger.",
    highlightAbove: 2000, highlightSeverity: "danger" },
  { key: "purchasePrediction", label: "Prediction",  type: "text",    width: 200,
    tooltip: "Decision tag from compute_prediction(). BUY → order sent to TWS. Doji / Bearish / Price-increase-less-than / Low activity → no order. Green check next to BUY = order was Filled.",
    showFillCheck: true },
  { key: "trade_activity_seconds", label: "Active Sec", type: "number", width: 100,
    tooltip: "Number of unique seconds in the current minute that had VOL-eligible activity at the moment the signal fired. Same metric the C++ passes_activity_check evaluates against (active > sec × low_activity_threshold). High = healthy distributed momentum; low = pop-and-drop pattern." },
  { key: "close",              label: "Close",       type: "decimal", width: 100,
    tooltip: "Last price of the current minute's candle at the moment the signal fired." },
  { key: "open",               label: "Open",        type: "decimal", width: 100,
    tooltip: "First-trade price of the current minute's candle (after condition + size gates)." },
  // Hidden 2026-05-06 — keep for future use.
  // { key: "high",               label: "High",        type: "decimal", width: 100,
  //   tooltip: "Highest price seen in the current minute's candle." },
  // { key: "low",                label: "Low",         type: "decimal", width: 100,
  //   tooltip: "Lowest price seen in the current minute's candle." },
  { key: "volume",             label: "Cum. Volume", type: "number",  width: 120,
    tooltip: "Cumulative volume accepted into the minute's candle (only ticks with size ≥ MIN_TRADE_SIZE and a VOL-allowing condition)." },
  { key: "relative_volume",    label: "Rel. Vol.",   type: "decimal", width: 110,
    tooltip: "RV factor = candle.volume / hourly baseline from RelativeVolumeRatioHour. Threshold for firing lives in trading_config.json." },
  // Hidden 2026-05-06 — keep for future use.
  // { key: "vwap",               label: "VWAP",        type: "decimal", width: 100,
  //   tooltip: "Volume-weighted average price (legacy column — not populated by the C++ trader)." },
  { key: "ask_price",          label: "Ask",         type: "decimal", width: 100,
    tooltip: "Best ask from the latest Q.* quote at signal time. 0 = no fresh quote (>5 s old or symbol never quoted)." },
  { key: "ask_timestamp",      label: "Ask Time",    type: "local_time_ms", width: 130,
    tooltip: "Polygon SIP timestamp of the quote that produced ask_price. NULL = no fresh quote at signal time. Compare against Trade Time to gauge quote staleness." },
  { key: "ask_age_ms",         label: "Ask Age (ms)", type: "number", width: 120,
    tooltip: "How old the ask quote was at signal time = (Local Time × 1000) − Ask Time Stamp. Higher = the C++ trader fired with a staler NBBO. Blank when no fresh quote was available.",
    // Local Time is DOUBLE unix seconds (with fraction); Ask Time
    // Stamp is BIGINT unix ms. Convert seconds → ms then subtract.
    // Returns null when ask_timestamp is missing/0 so the cell stays
    // blank instead of showing a meaningless "1778076316800" delta.
    computed: (row) => {
      const askMs = Number(row.ask_timestamp);
      const localSec = Number(row.timestamp);
      if (!Number.isFinite(askMs) || askMs <= 0) return null;
      if (!Number.isFinite(localSec)) return null;
      return Math.round(localSec * 1000 - askMs);
    },
  },
  { key: "last_trade_price",   label: "Last",        type: "decimal", width: 100,
    tooltip: "Most recent trade price for this symbol at signal time." },
  { key: "exchange",           label: "Exchange",    type: "text",    width: 90,
    tooltip: "Polygon exchange code of the trade that triggered the signal (e.g. 4=NYSE Arca, 11=NYSE)." },
  { key: "trade_id",           label: "Trade ID",    type: "number",  width: 160,
    tooltip: "Polygon's unique tick identifier (i field). Combined with exchange + trf_id, this uniquely identifies the trade." },
  { key: "trf_id",             label: "TRF ID",      type: "number",  width: 100,
    tooltip: "Trade Reporting Facility ID for off-exchange prints. 0 means on-exchange." },
  { key: "low_float",          label: "Low Float",   type: "text",    width: 110,
    tooltip: "Float bucket label (legacy — currently empty placeholder; the C++ trader doesn't populate it yet)." },
  { key: "newsCount",          label: "News",        type: "number",  width: 80,
    tooltip: "Number of headlines IB returned within news_window_seconds of the BUY firing. Filled by the C++ news_catalyst thread (clientId 30) via reqHistoricalNews. 0 = either no news, or your IB account is not subscribed to a news provider.",
    highlightAbove: 0, highlightSeverity: "success" },
  { key: "news_metadata",      label: "Headline",    type: "text",    width: 360,
    tooltip: "First headline returned by the IB news catalyst lookup (newline-collapsed, single quotes stripped). Empty when newsCount=0." },
  { key: "timestamp_news",     label: "News Time",   type: "iso_local_timestamp", width: 180,
    tooltip: "MySQL NOW() at the moment the news_catalyst worker UPDATEd this row. Distinct from `timestamp` (signal fire) — the gap is the IB news round-trip." },
];

export const SIGNALS_COLUMN_WHITELIST = new Set(dbColumnKeys(SIGNALS_COLUMNS));
export const SIGNALS_DEFAULT_SORT = { column: "timestamp", dir: "desc" as const };


// ── Orders ───────────────────────────────────────────────────────

export const ORDERS_TABLE = "Orders";

export const ORDERS_COLUMNS: ColumnDef[] = [
  { key: "id",                    label: "ID",          type: "number",                     width: 80,
    tooltip: "Auto-incremented row ID assigned by MySQL." },
  { key: "symbol",                label: "Symbol",      type: "text",                       width: 90,
    tooltip: "Stock ticker for this order." },
  { key: "start_timestamp",       label: "Local Time",       type: "local_time_decimal_seconds", width: 150,
    tooltip: "Wall clock when the WebSocket frame holding this trade arrived in the reader thread (carried via ring1)." },
  { key: "end_timestamp",         label: "End time process", type: "local_time_decimal_seconds", width: 160,
    tooltip: "Wall clock when this row was emitted. Persister 'Processing' rows: end of process_trade. ib_executor rows: when TWS returned a terminal status." },
  {
    key: "duration_us",
    label: "Duration (µs)",
    type: "decimal",
    decimals: 1,
    width: 140,
    highlightAbove: 10,
    formatAsMsForStatuses: ["Filled", "Not executed"],
    tooltip: "(end − start) × 10⁶. Processing rows = pure C++ pipeline cost (µs, > 10 µs flagged orange). Filled / Not executed = pipeline + TWS round-trip — shown in ms with no warning, since IB latency is inherent.",
    // (end_timestamp − start_timestamp) × 1,000,000 → microseconds.
    // Both columns are MySQL DECIMAL(20,7) returned as strings; convert
    // via Number for the arithmetic — DOUBLE has plenty of precision
    // for this small delta.
    computed: (row) => {
      const start = Number(row.start_timestamp);
      const end   = Number(row.end_timestamp);
      if (!Number.isFinite(start) || !Number.isFinite(end)) return null;
      return (end - start) * 1e6;
    },
  },
  { key: "status",                label: "Status",      type: "text",                       width: 110,
    tooltip: "'Processing' (persister snapshot at signal fire) | 'Filled' (TWS confirmed fill) | 'Not executed' (TWS rejected, timed out, or market closed).",
    greenWhenValue: "Filled" },
  { key: "orderType",             label: "Type",        type: "text",                       width: 80,
    tooltip: "BUY or SELL. Currently only BUY orders are emitted." },
  { key: "filledPrice",           label: "Filled",      type: "decimal",                    width: 100,
    tooltip: "Average fill price reported by TWS. Equals the limit price when status is 'Not executed'." },
  { key: "totalQuantity",         label: "Qty",         type: "number",                     width: 90,
    tooltip: "Number of shares ordered (currently hardcoded at 100 in the C++ trader)." },
  { key: "open_price",            label: "Open Px",     type: "decimal",                    width: 100,
    tooltip: "Candle open at the moment the signal fired." },
  { key: "polygon_second_close",  label: "Sec Close",   type: "decimal",                    width: 110,
    tooltip: "Per-second aggregate close price (legacy — not populated by the C++ trader)." },
  { key: "ask_price",             label: "Ask",         type: "decimal",                    width: 100,
    tooltip: "Best ask from the latest Q.* quote at order time. 0 = no fresh quote (>5 s)." },
  { key: "ask_size",              label: "Ask sz",      type: "number",                     width: 90,
    tooltip: "Shares offered at ask_price by the exchange showing the best ask." },
  { key: "bid_price",             label: "Bid",         type: "decimal",                    width: 100,
    tooltip: "Best bid from the latest Q.* quote at order time. 0 = no fresh quote (>5 s)." },
  { key: "bid_size",              label: "Bid sz",      type: "number",                     width: 90,
    tooltip: "Shares bid at bid_price by the exchange showing the best bid." },
  { key: "ask_timestamp",         label: "Quote Time",  type: "local_time_ms",              width: 130,
    tooltip: "Polygon SIP timestamp of the quote that produced bid/ask above. NULL = no fresh quote." },
  { key: "last_trade_price",      label: "Last Px",     type: "decimal",                    width: 100,
    tooltip: "Price of the trade tick that triggered this order." },
  { key: "log",                   label: "IB Log",      type: "text",                       width: 600,
    tooltip: "Full TWS response: status + fill info, or warning/error text (e.g. after-hours warning, rejection reason). Newlines collapsed to spaces." },
];

// Whitelist excludes computed columns — they don't exist in the DB and
// would error if used for SELECT / WHERE / ORDER BY.
export const ORDERS_COLUMN_WHITELIST = new Set(dbColumnKeys(ORDERS_COLUMNS));
export const ORDERS_DEFAULT_SORT = { column: "id", dir: "desc" as const };


// ── Stocks ───────────────────────────────────────────────────────
// Master symbol registry — one row per ticker. Slow-changing reference
// data (float, shares_outstanding, last close).

export const STOCKS_TABLE = "Stocks";

export const STOCKS_COLUMNS: ColumnDef[] = [
  { key: "id",                  label: "ID",                 type: "number",  width: 70,
    tooltip: "Auto-incremented row ID." },
  { key: "ticker",               label: "Ticker",             type: "text",    width: 100,
    tooltip: "Stock ticker symbol (master registry — one row per symbol)." },
  { key: "close",                label: "Last Close",         type: "decimal", width: 120,
    tooltip: "Most recent session's closing price. Populated by get_previous_close.py during pre-market data pipeline." },
  { key: "float_value",          label: "Float",              type: "number_abbreviated", width: 140,
    tooltip: "Public float — number of shares available for trading (excludes restricted/insider shares). Populated by get_float.py from Yahoo Finance." },
  { key: "short_percent_float",  label: "Short %",            type: "number",  width: 110,
    tooltip: "Short interest expressed as percentage of float (Yahoo precomputed). ≥ 5 % flags the symbol for the short-squeeze signal branch." },
  { key: "short_finviz",         label: "Short % (Finviz)",   type: "number",  width: 130,
    tooltip: "Cross-validation column — Finviz scrape of Short Float. Currently NULL; populated by a future validation step that will compare Yahoo vs Finviz vs StockAnalysis when Yahoo Short% > 10%." },
  { key: "short_stockanalysis",  label: "Short % (SA)",       type: "number",  width: 130,
    tooltip: "Cross-validation column — stockanalysis.com scrape of Short % of Float. Currently NULL; populated by the same future validation step as short_finviz." },
  { key: "avg_month_volume",     label: "Avg Month Volume",   type: "number",  width: 170,
    tooltip: "30-day average daily volume." },
  { key: "shares_outstanding",   label: "Shares Outstanding", type: "number_abbreviated", width: 170,
    tooltip: "Total shares issued by the company (float + restricted/insider)." },
  { key: "shares_short",         label: "Shares Short",       type: "number_abbreviated", width: 140,
    tooltip: "Absolute count of shares currently sold short." },
];

export const STOCKS_COLUMN_WHITELIST = new Set(dbColumnKeys(STOCKS_COLUMNS));
export const STOCKS_DEFAULT_SORT = { column: "ticker", dir: "asc" as const };


// ── RelativeVolumeRatioHour ──────────────────────────────────────
// Per-symbol, per-hour-of-day volume baseline used by the C++ RV
// filter. ~10K rows (~600 symbols × 24 hour buckets).

export const RV_TABLE = "RelativeVolumeRatioHour";

export const RV_COLUMNS: ColumnDef[] = [
  { key: "id",              label: "ID",              type: "number", width: 90,
    tooltip: "Auto-incremented row ID." },
  { key: "symbol",          label: "Symbol",          type: "text",   width: 110,
    tooltip: "Stock ticker." },
  { key: "hour",            label: "Hour (1–12)",     type: "number", width: 120,
    tooltip: "Hour of the day on a 12-hour clock (combined with AM/PM forms one of 24 buckets)." },
  { key: "amPm",            label: "AM/PM",           type: "text",   width: 90,
    tooltip: "AM/PM marker that pairs with Hour to form the 24-bucket key." },
  { key: "relative_volume", label: "Baseline Volume", type: "number", width: 160,
    tooltip: "Historical average minute-volume for this (symbol, hour, AM/PM) bucket. The C++ RV filter divides current candle volume by this value." },
];

export const RV_COLUMN_WHITELIST = new Set(dbColumnKeys(RV_COLUMNS));
export const RV_DEFAULT_SORT = { column: "symbol", dir: "asc" as const };


// ── minute_candlesticks ──────────────────────────────────────────
// Per-symbol, per-minute snapshot written by the C++ trader at every
// minute rollover (one row per known symbol, including those with
// volume=0). Source for the volume-freshness filter (Python's
// get_average_volume_limit), not yet ported to C++.

export const MINUTE_CANDLES_TABLE = "minute_candlesticks";

export const MINUTE_CANDLES_COLUMNS: ColumnDef[] = [
  { key: "stock_symbol", label: "Symbol",      type: "text",    width: 120,
    tooltip: "Stock ticker." },
  { key: "timestamp",    label: "Timestamp",   type: "text",    width: 200,
    tooltip: "Local minute boundary at which the candle was flushed." },
  { key: "volume",       label: "Volume",      type: "number",  width: 140,
    tooltip: "Cumulative volume of the just-ended minute (Block 2-gated; size ≥ MIN_TRADE_SIZE)." },
  { key: "close_price",  label: "Close",       type: "decimal", width: 120, decimals: 3,
    tooltip: "Close price of the just-ended minute (Block 1-gated)." },
];

export const MINUTE_CANDLES_COLUMN_WHITELIST = new Set(dbColumnKeys(MINUTE_CANDLES_COLUMNS));
export const MINUTE_CANDLES_DEFAULT_SORT = { column: "timestamp", dir: "desc" as const };


// ── Portfolio ────────────────────────────────────────────────────
// Snapshot of the IB account positions, refreshed every time the
// C++ trader starts up (TRUNCATE + INSERT). Mirrors what the
// operator sees in TWS at boot — useful for "what am I already
// holding from previous sessions?".
//
// The table is rendered as TWO grids on /portfolio:
//   - HELD  → rows where sold_at IS NULL     → /api/portfolio
//   - SOLD  → rows where sold_at IS NOT NULL → /api/portfolio/sold
// Hence two column sets below — held shows live Last + P&L %, sold
// shows the historical exit info instead.

export const PORTFOLIO_TABLE = "Portfolio";

// Held positions — live, refreshed every 5 s. Last and % are virtual
// columns enriched by the route handler from Polygon's snapshot.
export const PORTFOLIO_HELD_COLUMNS: ColumnDef[] = [
  { key: "symbol",        label: "Symbol",      type: "text",             width: 110,
    tooltip: "Stock ticker as reported by IB's reqPositions() callback." },
  { key: "position",      label: "Position",    type: "number",           width: 100,
    tooltip: "Number of shares held. Equivalent to TWS's POS column." },
  { key: "avg_cost",      label: "Avg Cost",    type: "decimal", width: 110,
    tooltip: "Average price per share you paid (TWS 'AVG PX'). Reported by IB's position() callback." },
  { key: "last_price",    label: "Last",        type: "decimal", width: 110,
    tooltip: "Most recent trade price from Polygon's snapshot endpoint. Refreshed on every 5-second poll. Green up-arrow = above Avg Cost (in profit), red down-arrow = below Avg Cost (in drawdown).",
    computed: (row) => (typeof row.last_price === "number" ? row.last_price : null),
    trendVsKey: "avg_cost" },
  { key: "pnl_pct",       label: "%",           type: "decimal", width: 100,
    tooltip: "Live P&L percentage: (Last − Avg Cost) / Avg Cost × 100. Green when in profit, red when in drawdown. Recomputed on every 5-second refresh alongside Last.",
    computed: (row) => {
      const last = Number(row.last_price);
      const avg  = Number(row.avg_cost);
      if (!Number.isFinite(last) || !Number.isFinite(avg) || avg === 0) return null;
      return ((last - avg) / avg) * 100;
    },
    pctColored: true },
  { key: "account",       label: "Account",     type: "text",             width: 130,
    tooltip: "IB account ID that owns this position (you can have multiple sub-accounts)." },
  { key: "snapshot_time", label: "Snapshot",    type: "iso_local_timestamp", width: 180,
    tooltip: "When the C++ trader pulled this snapshot from IB. Refreshes on every --persist startup." },
];

export const PORTFOLIO_HELD_COLUMN_WHITELIST = new Set(dbColumnKeys(PORTFOLIO_HELD_COLUMNS));
export const PORTFOLIO_HELD_DEFAULT_SORT = { column: "symbol", dir: "asc" as const };

// Sold history — frozen, no auto-refresh. Records each exit during
// the current session: when, why, and the buy info preserved
// alongside so the operator can do a buy-vs-sell post-mortem.
//
// `sold_price` and `sold_pct` are derived from the `sold_reason`
// string written by the C++ position manager, which has the fixed
// shape:
//
//   "STOP_LOSS @ -5.13% (cost=1.5600 tick=1.4800)"
//   "TAKE_PROFIT @ +12.40% (cost=2.0000 tick=2.2480)"
//
// (see cpp_ultra_low_latency/trade_processor.h — the snprintf in the
// stop-loss / take-profit branch). Parsing client-side avoids
// touching the C++ trader or adding new MySQL columns.
export const PORTFOLIO_SOLD_COLUMNS: ColumnDef[] = [
  { key: "symbol",        label: "Symbol",      type: "text",             width: 110,
    tooltip: "Stock ticker." },
  { key: "position",      label: "Position",    type: "number",           width: 100,
    tooltip: "Shares originally bought." },
  { key: "avg_cost",      label: "Avg Cost",    type: "decimal", width: 110,
    tooltip: "Average price per share paid (preserved from the IB snapshot at startup)." },
  { key: "sold_price",    label: "Exit",        type: "decimal", width: 110,
    tooltip: "Trigger tick price that fired the SELL — extracted from sold_reason's `tick=` field. Green up-arrow = sold above cost (profit), red down-arrow = sold below cost (loss).",
    computed: (row) => {
      const r = typeof row.sold_reason === "string" ? row.sold_reason : "";
      const m = r.match(/tick=([0-9.]+)/);
      return m ? Number(m[1]) : null;
    },
    trendVsKey: "avg_cost" },
  { key: "sold_pct",      label: "%",           type: "decimal", width: 100,
    tooltip: "Realised P&L percentage at exit — extracted from sold_reason's `@ ±X.XX%` field. Green = profit (TAKE_PROFIT), red = loss (STOP_LOSS).",
    computed: (row) => {
      const r = typeof row.sold_reason === "string" ? row.sold_reason : "";
      const m = r.match(/@\s*([+\-]?\d+\.\d+)%/);
      return m ? Number(m[1]) : null;
    },
    pctColored: true },
  { key: "account",       label: "Account",     type: "text",             width: 130,
    tooltip: "IB account ID." },
  { key: "snapshot_time", label: "Snapshot",    type: "iso_local_timestamp", width: 180,
    tooltip: "When the C++ trader pulled this snapshot from IB at startup." },
  { key: "sold_at",       label: "Sold At",     type: "iso_local_timestamp", width: 180,
    tooltip: "Wall-clock when the position manager sold this position during the current session." },
  { key: "sold_reason",   label: "Sold reason", type: "text",                width: 360,
    tooltip: "Why the SELL fired — STOP_LOSS (orange tint) or TAKE_PROFIT (green tint). Includes avg cost and triggering tick price.",
    rowClassByPrefix: [
      { prefix: "STOP_LOSS",   className: "row-stop-loss"  },
      { prefix: "TAKE_PROFIT", className: "row-take-profit" },
    ] },
];

export const PORTFOLIO_SOLD_COLUMN_WHITELIST = new Set(dbColumnKeys(PORTFOLIO_SOLD_COLUMNS));
export const PORTFOLIO_SOLD_DEFAULT_SORT = { column: "sold_at", dir: "desc" as const };


// ── Low Float (view of Stocks) ───────────────────────────────────
// Same MySQL table as Stocks, but exposed as a dedicated page that
// pre-filters to the strategy's universe: low float (< 10M shares) and
// price within the configured trading range. Mirrors the legacy
// `get_low_float_stocks()` helper in `../../../get_float.py` — the
// strategy's primary scanner.
//
// The route handler appends an extraWhere clause that inlines the
// price range from trading_config.json at request time, so changes via
// /api/config show up here on the next refetch.

export const LOW_FLOAT_TABLE = "Stocks";

// Fallback hard cap on float for "low float" classification. Used
// ONLY when `trading_config.json` is missing the `low_float_threshold`
// field (back-compat). The JSON is the source of truth — edit it
// from /utils. Matches `LOW_FLOAT_THRESHOLD` in trading_config.py.
export const LOW_FLOAT_MAX_VALUE_FALLBACK = 10_000_000;

export const LOW_FLOAT_COLUMNS: ColumnDef[] = [
  { key: "ticker",              label: "Ticker",             type: "text",    width: 100,
    tooltip: "Stock ticker symbol." },
  { key: "shares_outstanding",  label: "Shares Outstanding", type: "number_abbreviated", width: 170,
    tooltip: "Total shares issued (float + restricted/insider). Denominator of the Short % calc. Rendered as 2.6 M / 685 K for readability." },
  { key: "float_value",         label: "Float",              type: "number_abbreviated", width: 140,
    tooltip: "Public float — shares available for trading (excludes insider / restricted holdings). The strategy targets stocks with float < 10M because each trade has more leverage on price in a small float. Rendered as 2.6 M / 685 K for readability." },
  { key: "close",               label: "Last Close",         type: "decimal", width: 120, decimals: 2, prefix: "$ ",
    tooltip: "Most recent close price. Must fall within the trading range from trading_config.json (min_price / max_price) for the stock to appear here." },
  { key: "shares_short",        label: "Shares Short",       type: "number_abbreviated", width: 140,
    tooltip: "Absolute count of shares currently sold short. Numerator of the Short % calc. Rendered as 2.6 M / 685 K for readability." },
  { key: "avg_month_volume",    label: "Avg Month Volume",   type: "number",  width: 170,
    tooltip: "30-day average daily volume — liquidity check. Low-float stocks with low volume are dangerous to trade (slippage)." },
  { key: "short_pct_calc",      label: "Short %",            type: "decimal", width: 120, decimals: 2, suffix: "%",
    tooltip: "Short interest as percentage of float — Yahoo's precomputed `shortPercentOfFloat` (matches the value displayed at finance.yahoo.com/quote/<sym>/key-statistics). Falls back to live shares_short / float_value × 100 if Yahoo's value is NULL. Sorted DESC by default so the most heavily-shorted candidates appear first. Green check when > 10% — squeeze candidate.",
    // Server-side SQL expression. Prefers Yahoo's precomputed
    // `short_percent_float` (stored as a 0..1 fraction → ×100 to render
    // as a percentage). Falls back to a live shares_short / float_value
    // calc if the column is NULL (e.g. after Step 3 ran but Yahoo's
    // backend didn't expose the field for this ticker). The MySQL
    // ORDER BY uses this alias on the result set, so the highest-shorted
    // stocks land on page 1.
    dbExpression: "COALESCE(short_percent_float * 100, CASE WHEN float_value > 0 THEN shares_short / float_value * 100 ELSE NULL END)",
    highlightAbove: 10,
    highlightSeverity: "success" },
  { key: "short_finviz",        label: "Short % (Finviz)",   type: "decimal", width: 140, decimals: 2, suffix: "%",
    tooltip: "Cross-validation source — scraped from Finviz (Short Float row on the quote page). Populated by Step 3 of the data pipeline ONLY when Yahoo Short% > 10% (saves ~390 fetches/run). Stored as a 0..1 fraction in MySQL → ×100 for display. Blank when below threshold or scrape failed.",
    dbExpression: "short_finviz * 100" },
  { key: "short_stockanalysis", label: "Short % (SA)",       type: "decimal", width: 140, decimals: 2, suffix: "%",
    tooltip: "Cross-validation source — scraped from stockanalysis.com (Short % of Float row on the statistics page). Populated by Step 3 of the data pipeline ONLY when Yahoo Short% > 10%. Stored as a 0..1 fraction in MySQL → ×100 for display. Blank when below threshold or scrape failed.",
    dbExpression: "short_stockanalysis * 100" },
];

export const LOW_FLOAT_COLUMN_WHITELIST = new Set(dbColumnKeys(LOW_FLOAT_COLUMNS));
export const LOW_FLOAT_DEFAULT_SORT = { column: "short_pct_calc", dir: "desc" as const };


// ── RawTrades ────────────────────────────────────────────────────
// Tick-level trades downloaded from Polygon.io for a single
// (symbol, year, month, day, hour, minute). Populated by the
// /raw-trades page (POST /api/raw-trades/run).

export const RAW_TRADES_TABLE = "RawTrades";

export const RAW_TRADES_COLUMNS: ColumnDef[] = [
  { key: "id",         label: "ID",         type: "number",              width: 90,
    tooltip: "Auto-incremented row ID assigned at download time." },
  { key: "symbol",     label: "Symbol",     type: "text",                width: 90,
    tooltip: "Stock ticker for this tick." },
  { key: "close",      label: "Price",      type: "decimal",             width: 170,
    tooltip: "Trade execution price reported by Polygon." },
  { key: "volume",     label: "Size",       type: "number",              width: 100,
    tooltip: "Number of shares in this print." },
  { key: "timestamp",  label: "Date",       type: "iso_local_date",      width: 120,
    tooltip: "Date portion of the SIP timestamp converted to local time." },
  {
    key: "timestamp_time",
    label: "Time",
    type: "iso_local_time",
    width: 150,
    tooltip: "Time portion (HH:MM:SS.µs) of the SIP timestamp — when the trade actually happened on the exchange.",
    // Virtual column — formatter pulls the time slice out of the same
    // ISO string the "Date" column already shows. Sort/filter happen on
    // the underlying `timestamp` column.
    computed: (row) => (typeof row.timestamp === "string" ? row.timestamp : null),
  },
  { key: "second",     label: "Sec",        type: "text",                width: 70,
    tooltip: "Second-of-minute (0–59), for grouping ticks that fall in the same second." },
  // Virtual column — populated by getCellPrefix in raw-trades/page.tsx
  // using the OHLC walker's per-row low-activity flag. Mirrors the C++
  // passes_activity_check: at the moment this trade arrived, was the
  // count of unique seconds with VOL-eligible activity below
  // `elapsed × low_activity_threshold` (default 0.33)?
  // If yes → "Low activity" badge in amber. Else → cell empty.
  { key: "_activity_status", label: "Activity", type: "text",            width: 110,
    tooltip: "Low activity flag — set when the cumulative seconds-with-activity at this trade's moment falls under the configured threshold (matches the C++ passes_activity_check that demotes BUY signals to LOW_ACTIVITY).",
    computed: () => "" },   // default blank; getCellPrefix injects the badge when applicable
  { key: "exchange",   label: "Exchange",   type: "text",                width: 90,
    tooltip: "Polygon exchange code that reported this trade." },
  { key: "trade_id",   label: "Trade ID",   type: "text",                width: 160,
    tooltip: "Polygon's unique tick identifier (i field)." },
  { key: "trf_id",     label: "TRF ID",     type: "text",                width: 110,
    tooltip: "Trade Reporting Facility ID. Set for off-exchange prints." },
  { key: "conditions", label: "Conditions", type: "text",                width: 160,
    tooltip: "Polygon trade-condition codes — gate which OHLCV components this tick is allowed to update (open/close, high/low, volume)." },
];

export const RAW_TRADES_COLUMN_WHITELIST = new Set(dbColumnKeys(RAW_TRADES_COLUMNS));
export const RAW_TRADES_DEFAULT_SORT = { column: "id", dir: "asc" as const };


// ── RawQuotes — historical NBBO snapshots downloaded alongside trades ──

export const RAW_QUOTES_TABLE = "RawQuotes";

export const RAW_QUOTES_COLUMNS: ColumnDef[] = [
  { key: "id",            label: "ID",         type: "number",         width: 80,
    tooltip: "Auto-incremented row ID assigned at download time." },
  { key: "symbol",        label: "Symbol",     type: "text",           width: 80,
    tooltip: "Stock ticker for this quote snapshot." },
  { key: "bid_price",     label: "Bid",        type: "decimal",        width: 100,
    tooltip: "Best bid price at this NBBO snapshot." },
  { key: "bid_size",      label: "Bid sz",     type: "number",         width: 90,
    tooltip: "Shares displayed at the best bid (top-of-book)." },
  { key: "ask_price",     label: "Ask",        type: "decimal",        width: 100,
    tooltip: "Best ask price at this NBBO snapshot." },
  { key: "ask_size",      label: "Ask sz",     type: "number",         width: 90,
    tooltip: "Shares displayed at the best ask (top-of-book)." },
  { key: "spread",        label: "Spread",     type: "decimal",        width: 90,
    tooltip: "Ask − bid. Compression = MMs active; widening = MMs retreating." },
  { key: "timestamp",     label: "Time",       type: "iso_local_time", width: 130,
    tooltip: "SIP timestamp of this NBBO update converted to local time." },
  { key: "bid_exchange",  label: "Bid ex",     type: "text",           width: 80,
    tooltip: "Polygon exchange code that posted the best bid." },
  { key: "ask_exchange",  label: "Ask ex",     type: "text",           width: 80,
    tooltip: "Polygon exchange code that posted the best ask." },
  { key: "conditions",    label: "Cond",       type: "text",           width: 100,
    tooltip: "Quote condition codes (Polygon)." },
  { key: "tape",          label: "Tape",       type: "number",         width: 70,
    tooltip: "Tape (1=NYSE, 2=AMEX, 3=NASDAQ)." },
];

export const RAW_QUOTES_COLUMN_WHITELIST = new Set(dbColumnKeys(RAW_QUOTES_COLUMNS));
export const RAW_QUOTES_DEFAULT_SORT = { column: "id", dir: "asc" as const };
