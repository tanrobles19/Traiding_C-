@AGENTS.md

# Trading Dashboard

Read-only web dashboard for the C++ trading system that lives in
`../cpp_ultra_low_latency/`. Browses MySQL tables (`TradeSignalsBuyPerSecond`,
`Orders`, …) with server-side pagination, filtering, and 5-second auto-refresh.

## Hard rules

- **Never modify the C++ system.** Anything in `../cpp_ultra_low_latency/`
  is off-limits. The dashboard reads the same MySQL database; it does not
  share code, processes, or files with the trading system.
- **Local only.** No auth, no SSL, no remote hosting. Runs on the same
  machine as the C++ trader, against `localhost:3306`.
- **Replaces the Python TUIs** (`ui_experiments.py`, `utils_dashboard.py`,
  `experimental_dashboard.py`). They will be retired as parity grows here.
- **Mostly read-only — narrow write surface.** A small set of admin
  actions is allowed and explicitly enumerated below. Anything else is
  read-only.

## Allowed write actions

The dashboard exposes exactly these mutating endpoints:

| Method | Path | Effect |
|---|---|---|
| `POST` | `/api/stocks` | Insert one row into `Stocks`. Body is `{ticker, close?, float_value?, short_percent_float?, avg_month_volume?, shares_outstanding?, shares_short?}`. Ticker is uppercased, validated `^[A-Z][A-Z0-9._\-]{0,9}$`. |
| `DELETE` | `/api/stocks/:id` | Remove one row from `Stocks` by primary key. |
| `POST` | `/api/signals/clear` | `TRUNCATE TABLE TradeSignalsBuyPerSecond`. |
| `POST` | `/api/orders/clear` | `TRUNCATE TABLE Orders`. |
| `POST` | `/api/utils/run`  | Spawns the Python data pipeline (`../utils_pipeline.py`). Body `{steps: {clear, last_price, float, historical, rv}}` — each key is a boolean; `true` runs the step, `false` skips it. Refuses concurrent runs (409). See *Data Pipeline page* for the per-step semantics and the destructive Step 1 (truncates `HistoryByMin` + day-work tables). |
| `POST` | `/api/utils/stop` | SIGTERM the active pipeline child, if any. Returns 200 `{stopped:true}` on success, 409 if no run is in flight. |
| `PUT`  | `/api/config`     | Writes `../trading_config.json` (atomic `.tmp` + rename). Body keys: `relative_volume_factor`, `increase_from_open_pct`, `min_trade_size`, `low_activity_threshold`, `order_quantity`, `float_threshold`, `min_price`, `max_price`, `trade_capital`, `max_loss_tolerance_pct`. Each must be a finite number. C++ trader picks up changes on next `--persist` start; Python pipeline picks them up on next run. |

There is **no** clear-all action for `Stocks` — it's intentionally
omitted because the table is the master symbol registry that the C++
system depends on at startup. Wiping it would break the next pre-market
pipeline run.

All other tables remain strictly read-only via the dashboard.

UI affordances:

- **Stocks page** — `Add stock` button (top-right) opens a modal form;
  per-row trash icon (rightmost pinned column) deletes a single ticker
  after a confirm dialog.
- **Signals / Orders pages** — `Clear table` button (top-right) opens a
  destructive confirm dialog showing the row count, then truncates.

Each mutation invalidates the relevant TanStack Query keys so the table
re-fetches immediately, and the header counts update on the next 5-sec
poll.

## Tech stack

| Layer | Choice | Why |
|---|---|---|
| Framework | **Next.js 16** (App Router) + React 19 + TS | Server-side route handlers + client components in one process |
| Styling | **Tailwind v4** + shadcn/ui (Radix + Nova preset) | CSS-variable theme, dark forced on `<html>` |
| Tables | **AG Grid Community** (Quartz dark theme) | Virtual rendering, fast on 100-row page, scales to 1M-row tables via server pagination |
| Charts | **Recharts** | Top-symbols bar chart — light, dark-theme-friendly |
| DB driver | **mysql2/promise** with a 5-connection pool | Battle-tested, async, no ORM overhead |
| Query layer | Next.js Route Handlers (REST) | One process, no separate API server |
| Client cache | **TanStack Query** with `refetchInterval: 5000` | Single source of truth for "stale after 5 s" |
| Node | **22** (pinned via `.nvmrc`) | Next 16 requires ≥ 20 |

## How to run

```bash
nvm use 22                  # picks up .nvmrc
npm install                 # one time
npm run dev                 # http://localhost:3000
npm run build && npm start  # production build (used to surface type errors)
```

## Directory structure

```
trading_dashboard/
├── .nvmrc                  # 22
├── .env.local              # DB_HOST / PORT / USER / NAME / POLYGON_API_KEY (DB password hardcoded)
├── package.json
├── components.json         # shadcn config (Radix + Nova preset)
├── tsconfig.json
├── next.config.ts
├── postcss.config.mjs      # @tailwindcss/postcss
├── eslint.config.mjs
└── src/
    ├── app/
    │   ├── layout.tsx          # Shell: Providers → Sidebar + (Header + main)
    │   ├── page.tsx            # /  → overview tiles
    │   ├── signals/page.tsx    # /signals
    │   ├── orders/page.tsx     # /orders
    │   ├── stocks/page.tsx     # /stocks  (read + add + delete)
    │   ├── low-float/page.tsx  # /low-float   → Stocks pre-filtered to strategy universe
    │   ├── rv/page.tsx         # /rv          → RelativeVolumeRatioHour
    │   ├── run-status/page.tsx # /run-status  → C++ trader telemetry (CSV + DB)
    │   ├── utils/page.tsx      # /utils       → data pipeline runner
    │   ├── globals.css         # Tailwind v4 + shadcn theme variables
    │   └── api/
    │       ├── stats/route.ts             # GET — row counts (5-sec polled)
    │       ├── signals/route.ts           # GET — paginated TradeSignalsBuyPerSecond
    │       ├── signals/clear/route.ts     # POST — truncate signals
    │       ├── orders/route.ts            # GET — paginated Orders
    │       ├── orders/clear/route.ts      # POST — truncate orders
    │       ├── stocks/route.ts            # GET — paginated · POST — insert row
    │       ├── stocks/[id]/route.ts       # DELETE — remove one row
    │       ├── rv/route.ts                # GET — paginated RelativeVolumeRatioHour
    │       ├── run-status/route.ts        # GET — newest C++ telemetry CSV → aggregates + series
    │       ├── signal-latency/route.ts    # GET — TradeSignals.local_utc_timestamp aggregates
    │       ├── portfolio/route.ts         # GET — held positions (sold_at IS NULL) + Polygon last_price enrichment
    │       ├── portfolio/sold/route.ts    # GET — sold positions (sold_at IS NOT NULL), no enrichment, no polling
    │       ├── low-float/route.ts         # GET — Stocks pre-filtered to strategy universe (float < 10M + price range from JSON)
    │       ├── config/route.ts            # GET / PUT — trading_config.json
    │       ├── utils/run/route.ts         # POST — spawn pipeline, stream SSE; refuses concurrent runs
    │       ├── utils/stop/route.ts        # POST — SIGTERM the active pipeline child
    │       └── utils/info/route.ts        # GET — symbol info + table row counts
    ├── components/
    │   ├── Providers.tsx       # TanStack QueryClient
    │   ├── ThemeProvider.tsx   # Light / dark context, persisted in localStorage
    │   ├── ThemeToggle.tsx     # Sun/moon button in the header
    │   ├── Sidebar.tsx         # left nav with active-state highlight
    │   ├── Header.tsx          # title + counts + live clock + status dot + toggle
    │   ├── TablePage.tsx       # Shared shell: top toolbar + grid + pagination + chart
    │   ├── DataGrid.tsx        # AG Grid wrapper · per-column filter + click sort
    │   ├── Pagination.tsx      # first / prev / N of M / next / last
    │   ├── SymbolBarChart.tsx  # Recharts top-N symbols by row count
    │   ├── ConfirmDialog.tsx   # destructive-confirm modal (alert-dialog)
    │   ├── AddStockDialog.tsx  # Add-stock form modal
    │   ├── RowDeleteButton.tsx # per-row trash button used by AG Grid
    │   └── ui/                 # shadcn primitives (button, card, input, …)
    └── lib/
        ├── db.ts                  # mysql2 pool + query/count/execute helpers
        ├── query-builder.ts       # filters/sort/limit → safe SQL fragments
        ├── handlers.ts            # paginatedTableHandler — shared route logic + extraWhere
        ├── tables.ts              # per-table column metadata + whitelist
        ├── format.ts              # cell formatters (timestamp / decimal / int)
        ├── polygon.ts             # fetchLastTrades(symbols) — multi-ticker snapshot for /api/portfolio
        └── pipeline-process.ts    # Cross-route singleton holding the active utils_pipeline.py child
```

> `FilterBar.tsx` was retired — per-column filtering moved into AG Grid
> floating filters (see "Filtering & sorting" below).

## Data flow

```
Browser
  ├── TanStack Query (refetchInterval=5000)
  │     fetches /api/<table>?page=N&pageSize=100&filters=[…]&sort={…}
  │
  ├── AG Grid Community  ←  rows from cache
  ├── Recharts bar chart ←  rows from cache
  └── FilterBar + Pagination  →  setState  →  new query key  →  new fetch
                                                       ↓
                                            Next.js Route Handler
                                                       ↓
                                          query-builder → SQL string
                                                       ↓
                                                mysql2 pool (5 connections)
                                                       ↓
                                                MySQL `histFinanData`
```

Every table page funnels through the same `TablePage` component. Per-page
specifics (table name, columns, default sort, API path) are looked up from
`lib/tables.ts` and `app/api/<name>/route.ts`. Adding a new table is ~30
lines of code (see "Adding a new table page" below).

## SQL safety model

User input never reaches the SQL string. Two protections:

1. **Values are parameterized** via `?` placeholders. mysql2 handles
   escaping. We never do `${value}` in SQL.
2. **Column names are whitelisted**. AG Grid columns and filter columns
   come from the client, but `query-builder.ts` rejects any column not in
   the per-table `Set<string>` whitelist defined in `lib/tables.ts`. This
   blocks `' OR 1=1 --` style injection through column-name parameters
   (which `?` placeholders cannot guard against).

If a request asks for a column that isn't whitelisted, the route returns
`{ error: "Disallowed column: …" }` with HTTP 400.

## Computed columns & row highlighting

`ColumnDef` (in `lib/tables.ts`) supports several extra fields beyond
the basic `{key, label, type, width}`:

```ts
type ColumnDef = {
  key: string;
  label: string;
  type: "text" | "number" | "number_abbreviated" | "decimal" |
        "datetime_ms" | "datetime_double_seconds" | "datetime_decimal_seconds";
  width?: number;

  // Format precision for "decimal" cells (default 4).
  decimals?: number;

  // Client-side virtual column — value derived at render time from
  // the row, not selected from the DB. Excluded from SELECT / sort /
  // filter automatically.
  computed?: (row: Record<string, unknown>) => number | string | null;

  // Server-side computed column — SQL expression that produces the
  // value at SELECT time. The column is sortable (MySQL accepts
  // aliases in ORDER BY) but NOT filterable (aliases don't work in
  // WHERE; DataGrid auto-disables the floating filter).
  dbExpression?: string;

  // Threshold for cell highlighting. Cell renders bold + colored with
  // an icon when value exceeds the threshold. See severity below for
  // color/icon/row-tint behavior.
  highlightAbove?: number;

  // Severity of the threshold:
  //   "warning" (default)  amber AlertTriangle · row tinted amber
  //   "danger"             red OctagonAlert · row NOT tinted
  //   "success"            emerald CheckCircle2 · row NOT tinted
  // "warning" is the only severity that tints the whole row — the
  // other two decorate the cell only so the table doesn't flood when
  // many rows match.
  highlightSeverity?: "warning" | "danger" | "success";
};
```

### Computed columns — two flavors

| Flavor | Where the value is produced | Sortable | Filterable |
|---|---|---|---|
| `computed` (client-side) | JS callback at render time      | ❌ | ❌ |
| `dbExpression` (server-side) | SQL fragment at SELECT time  | ✅ (alias in ORDER BY) | ❌ (alias not allowed in WHERE) |
| (regular column)            | `\`column_name\`` in SELECT  | ✅ | ✅ |

Helpers in `lib/tables.ts`:

```ts
dbColumnKeys(cols)        // every key whose ColumnDef lacks `computed`
                          // — i.e. real DB columns AND dbExpression
                          // aliases. Used for SELECT projection +
                          // *_COLUMN_WHITELIST (sort/filter gates).

dbExpressionMap(cols)     // { key → SQL expression } for every column
                          // with a dbExpression. Passed to the handler
                          // as `selectExpressions`, which the handler
                          // uses to emit `(expr) AS \`key\`` in SELECT.
```

`DataGrid` renders client-side `computed` via AG Grid's `valueGetter`;
server-side `dbExpression` columns arrive as plain row fields under the
alias key. Both auto-disable the floating filter (no DB column to
WHERE against, in different ways).

`paginatedTableHandler` accepts a `selectExpressions: Record<key, sql>`
option for the server-side flavor. See *URL contract for table APIs*
below.

### Row highlighting

Any column with `highlightAbove` decorates the cell with a colored
icon + bold text when the value exceeds the threshold. The exact
color, icon, and row-tint behavior depend on `highlightSeverity`:

| Severity         | Cell color | Cell icon       | Row class added       |
|---|---|---|---|
| `warning` (default) | amber   | `AlertTriangle` ⚠ | `row-warning` (orange tint + amber rail) |
| `danger`          | red       | `OctagonAlert`  | none — cell only      |
| `success`         | emerald   | `CheckCircle2`  | none — cell only      |

`DataGrid` builds an AG Grid `rowClassRules` map that adds
`row-warning` whenever **any** `warning`-severity column on a row
exceeds its threshold. `danger` and `success` are explicitly excluded
from the row-tint map.

The `.row-warning` style lives in `app/globals.css`:

```css
.ag-theme-quartz .ag-row.row-warning,
.ag-theme-quartz-dark .ag-row.row-warning {
  background-color: rgba(245, 158, 11, 0.10) !important;
  box-shadow: inset 3px 0 0 0 rgb(245, 158, 11);
}
```

Current uses:
- `ORDERS_COLUMNS.duration_us` — `warning` at 10 µs (orange tint).
- `LOW_FLOAT_COLUMNS.short_pct_calc` — `success` at 10 % (emerald
  check, no row tint — squeeze candidate flag).

## URL contract for table APIs

`GET /api/<table>` query parameters:

| Param | Type | Default | Purpose |
|---|---|---|---|
| `page` | integer (0-based) | 0 | Page index |
| `pageSize` | integer (1–500) | 100 | Rows per page (clamped to 500) |
| `sort` | JSON `{column, dir: "asc"\|"desc"}` | per-table default | One-column sort |
| `filters` | JSON `[{column, op, value}, …]` | `[]` | AND of conditions |

Filter ops:
| Op | Meaning | SQL |
|---|---|---|
| `eq` | equals | `= ?` |
| `ne` | not equal | `<> ?` |
| `lt`, `le`, `gt`, `ge` | comparisons | `<`, `<=`, `>`, `>=` |
| `contains` | substring | `LIKE %v%` |
| `starts` | prefix | `LIKE v%` |
| `ends` | suffix | `LIKE %v` |

Response:
```json
{
  "rows":     [...],          // current page
  "total":    123456,         // COUNT(*) with the same WHERE
  "page":     0,
  "pageSize": 100,
  "sort":     {"column":"timestamp","dir":"desc"},
  "filters":  []
}
```

## Filtering & sorting (per column)

Filters and sort live **inside the column headers**, not in a separate
toolbar:

- **Filter** — a small input below each column header (AG Grid floating
  filter). Text columns get `agTextColumnFilter` (contains, equals,
  starts-with, ends-with). Numeric / decimal / datetime columns get
  `agNumberColumnFilter` (=, ≠, <, ≤, >, ≥).
- **Sort** — click the column header. Cycles asc → desc → none.

Both are wired to the existing server-side API. `DataGrid` listens to
AG Grid's `onFilterChanged` and `onSortChanged` events, translates the
AG Grid model into our `Filter[]` / `{column, dir}` contract, and
calls back into `TablePage`. `TablePage` updates state, the React
Query key changes, and the next page is fetched.

```
[user types in floating filter]
        │
        ▼
AG Grid onFilterChanged
        │   model = { symbol: { filterType:'text', type:'contains', filter:'NV' } }
        ▼
DataGrid maps to Filter[]
        │   filters = [{ column:'symbol', op:'contains', value:'NV' }]
        ▼
TablePage setFilters → query key changes → API refetch
```

Computed columns (e.g. Orders `duration_us`) stay un-sortable / un-
filterable because the DB doesn't know about them. AG Grid disables
those headers automatically based on the `computed` flag in `ColumnDef`.

The whitelist + parameterised SQL described in **SQL safety model**
still applies — the values from AG Grid land in `?` placeholders,
the column names are checked against the per-table `Set<string>`.

## Per-table reference

### TradeSignalsBuyPerSecond  (default sort: `timestamp DESC`)

Surfaced columns (subset — table has ~30 columns):
`timestamp, symbol, close, open, high, low, volume, relative_volume,
vwap, ask_price, last_trade_price, purchasePrediction, exchange, low_float`.

Field types are listed in `lib/tables.ts` so each gets the right
formatter (`timestamp` is a `DOUBLE` of unix seconds → rendered as ISO).

### Orders  (default sort: `id DESC`)

Surfaced columns (left → right):
`id, symbol, start_timestamp, end_timestamp, duration_us, status,
orderType, filledPrice, totalQuantity, open_price, polygon_second_close,
ask_price, bid_price, last_trade_price`.

`start_timestamp` and `end_timestamp` are `DECIMAL(20,7)` of unix seconds
(sub-second precision) — rendered as ISO via the `datetime_decimal_seconds`
formatter, which preserves all 7 fractional digits by parsing the raw
DB string instead of going through a JS `Date` (which would round to ms).

`duration_us` is a **virtual column** computed in the dashboard, not in
the database (`(end_timestamp − start_timestamp) × 1,000,000`). It
captures how long the C++ trading pipeline took to move the trade from
arrival in the WebSocket reader to "consumer done with it", excluding
the persister + MySQL write.

If `duration_us > 10`, the row is highlighted orange with a left rail
and a ⚠ icon next to the value. Threshold lives in `lib/tables.ts`:
```ts
{ key: "duration_us", ..., highlightAbove: 10 }
```

### RelativeVolumeRatioHour  (default sort: `symbol ASC`)

Per-symbol per-hour volume baseline used by the C++ RV filter.
~10K rows (~600 symbols × 24 hour-buckets).

Surfaced columns:
`id, symbol, hour, amPm, relative_volume`.

Read-only — populated by the data pipeline (`/utils` page or the
old TUI). The dashboard never inserts into this table.

### Stocks  (default sort: `ticker ASC`)

Master symbol registry — one row per ticker, ~3,000 rows. Slow-changing
reference data (float, shares_outstanding, last close).

Surfaced columns:
`id, ticker, close, float_value, short_percent_float, short_finviz,
short_stockanalysis, avg_month_volume, shares_outstanding, shares_short`.

`short_finviz` and `short_stockanalysis` are cross-validation columns
added 2026-05-04. They sit next to `short_percent_float` (the Yahoo
value) and are populated by Step 3 of the pipeline ONLY when Yahoo's
Short % exceeds 10 %. See *Short % calculation chain* below for the
full data sourcing rules.

The Stocks page intentionally omits the symbol-bar chart (every row is
already a unique ticker, so a "top symbols on this page" chart would be
trivial). The grid spans the full width.

### Portfolio  (held: `symbol ASC`  ·  sold: `sold_at DESC`)

IB account positions, written by the C++ trader at startup
(`main.cpp` — `TRUNCATE TABLE Portfolio` + per-row `INSERT`) and
updated on each filled SELL (`ib_executor.h::mark_portfolio_sold` —
`UPDATE Portfolio SET sold_at, sold_reason WHERE symbol`). One MySQL
table, but the dashboard renders **two stacked grids** on `/portfolio`
with different refresh policies — see the dedicated **Portfolio page
(`/portfolio`)** section below for the full architecture, the Polygon
last-price integration, and the regex parsing rules for `Exit` /
realised-`%` columns.

### Low Float (view of Stocks)  (default sort: `short_pct_calc DESC`)

Pre-filtered view of the same `Stocks` MySQL table — same backing data
as the `/stocks` page, but rendered through a strategy-focused lens.
The route hard-codes a low-float filter and reads the price range live
from `trading_config.json`, so the operator only sees tickers the
strategy might actually trade. See the dedicated **Low Float page
(`/low-float`)** section below for the SQL filter, the
`shares_short / shares_outstanding` Short % calc, the squeeze-candidate
green flag at > 10 %, and the data-quality caveat for outlier rows.

## System Status page (`/run-status`)

Telemetry of the most recent C++ trader run. Two data sources fused
into one page: the CSV that `summary_logger.h` writes every 5 s, and
the `TradeSignalsBuyPerSecond` table that the persister fills with
each fired signal.

### Why this page exists

A long market-open run showed our snapshot-style telemetry as **all
zeros** even though Polygon's WebSocket dashboard simultaneously
showed `Message Buffer` rising. Polygon support confirmed the
meaning of their chart:

> "When buffer size is non-zero, it means client side is out of
> computation power or network bandwidth to process all the data
> for the time."

Two things were missing on our side:

1. **A way to see the C++ trader's state from the browser** — the
   CSV exists on disk but nobody was reading it.
2. **Peak tracking between samples** — the C++ side now writes 5
   extra columns (`ring_depth_max`, `recvq_max_bytes`,
   `rcv_wnd_min_bytes`, `rcv_wnd_zero_count`, `ring_dropped_delta`).
   See the C++ CLAUDE.md, "Peak tracking" subsection of the
   `summary_logger.h` reference.

The new page surfaces both in one place and lets the operator
correlate "Polygon's Buffer ↑" with our own bottleneck attribution.

### Architecture

```
┌──────────────────────────┐    GET /api/run-status   ┌───────────────────────┐
│ /run-status page          │ ──────────────────────► │ Next.js Route Handler │
│ (browser, 5-s poll)       │                         │  (Node runtime)       │
│                           │                         │                       │
│  • health pills (×5)      │ ◄── JSON ────────────── │ readNewestCsv()       │
│  • KPI tiles (×6)         │                         │ parseCsv()            │
│  • time-series charts (×4)│                         │ aggregate + downsample│
│  • TradeSignals latency   │                         │                       │
│    section                │    GET /api/signal-     │                       │
│                           │     latency             │                       │
│                           │ ──────────────────────► │ MySQL                 │
│                           │ ◄── JSON ────────────── │ SELECT … FROM         │
└──────────────────────────┘                          │ TradeSignalsBuyPer-   │
                                                      │ Second                │
                                                      └───────────────────────┘
```

### Files

| Path | Purpose |
|---|---|
| `app/api/run-status/route.ts` | GET — finds newest `run_*.csv` in `../cpp_ultra_low_latency/logs/`, parses 29 columns, computes averages / percentiles / peaks / health classifications, returns the full per-tick series. Always uses the most recent file (lexicographic sort by name — the timestamp is in the filename). |
| `app/api/signal-latency/route.ts` | GET — `SELECT symbol, local_utc_timestamp, timestamp FROM TradeSignalsBuyPerSecond` and aggregates: avg, p50, p95, p99, min, max + top-10 latency peaks (with symbol + Costa Rica local time). Filters out NaN / negative latencies. |
| `app/run-status/page.tsx` | Page UI — health pills, KPI grid, 4 time-series charts (trades/sec, SIP latency on sqrt-scale Y, ring depth, CPU), latency section with 6 tiles + per-signal chart + top-10 peaks list. |

### Health classification

`/api/run-status` returns 5 indicators, each `green` / `yellow` /
`red`. Thresholds calibrated from typical runs:

| Indicator | Source | green | yellow | red |
|---|---|---|---|---|
| `latency`      | avg `sip_latency_ms`              | < 200 ms | < 1 s    | ≥ 1 s |
| `ring`         | max `ring_depth` as % of capacity | < 25 %   | < 50 %   | ≥ 50 % |
| `cpu`          | max `cpu_pct`                     | < 50 %   | < 80 %   | ≥ 80 % |
| `drops`        | total `ring_dropped`              | 0        | (n/a)    | > 0 |
| `backpressure` | count of samples where `tcp_rcv_wnd_bytes == 0` | 0 | (n/a) | > 0 |

The "drops" and "backpressure" pills are binary on purpose — any
non-zero value is bad enough to flag red. The new `rcv_wnd_zero_count`
and `ring_dropped_delta` peak columns let the source CSV reach the
red verdict even when the snapshot columns happened to read 0 at
print time.

### Costa Rica timezone

`/api/signal-latency` converts unix-second timestamps from MySQL
into Costa Rica local time before sending (sv-SE locale via
`Intl.DateTimeFormat` with `timeZone: "America/Costa_Rica"`,
fractional ms, space replaced with `T`). The CSV path doesn't need
conversion — `summary_logger.h` writes `timestamp_iso` already in
local time, no `Z` suffix. This makes both data sources display in
the same timezone with the same `shortIso()` regex on the page.

### Latency formatting

Values < 1000 ms render as `"234 ms"`. Values ≥ 1000 ms render as
`"2.6 s"` (1 decimal). Values ≥ 60 s render as `"1m 23s"`. The SIP
latency chart uses a **sqrt scale** with doubling ticks
(0, 20s, 40s, 80s, 160s, 320s, 640s) — heavy-tailed data otherwise
gets crushed by the rare 10-minute spike.

### Auto-loading

The route always serves the **newest** CSV — no UI needed. Drop a
new `run_*.csv` into `cpp_ultra_low_latency/logs/` (just by running
the C++ trader) and the page picks it up on the next 5-s poll.
Every run produces its own file (timestamp embedded in the name),
so previous runs are preserved on disk but the page only shows the
latest.

## Data Pipeline page (`/utils`)

Spawns the Python pre-market data pipeline (`../utils_pipeline.py`)
and streams its progress to the browser as Server-Sent Events. The
pipeline replaces the old Textual TUI (`../utils_dashboard.py`) with
the same workload but a five-step decomposition that lets the
operator skip steps already up-to-date for the day.

### Architecture

```
┌─────────────────┐    POST /api/utils/run        ┌──────────────────────┐
│ /utils page     │ ─────────────────────────► │ Next.js Route Handler   │
│  (browser)      │  body: {steps:{clear, last_  │  (Node runtime)         │
│                 │   price, float, historical,  │                         │
│                 │   rv}}                       │                         │
└──────┬──────────┘                              └──────────┬─────────────┘
       │                                                    │
       │  ReadableStream (SSE: data: {…} per event)         │
       │ ◄──────────────────────────────────────────────────┤
       │                                                    │ spawn(python3,
       │                                                    │  ../utils_pipeline.py
       │                                                    │  [--skip-<step> …])
       │                                                    ▼
       │     ┌──────────────────────────────────────────────────────────┐
       │     │ Python: utils_pipeline.py                                │
       │     │   step 1  clear day-work tables (clean_db)               │
       │     │   step 2  last_price → Stocks.close (Polygon)            │
       │     │   step 3  float      → Stocks.float_value (yfinance)     │
       │     │   step 4  historical → HistoryByMin (Polygon)            │
       │     │   step 5  rv         → RelativeVolumeRatioHour           │
       │     │   stdout = JSON events per line                          │
       │     └─────────────────────────┬────────────────────────────────┘
       │                               │
       │                               ▼
       │                            MySQL
       └─ updates 5 step cards live as events arrive

Stop:  POST /api/utils/stop  →  killActiveChild("SIGTERM")
                            (singleton in lib/pipeline-process.ts;
                             the running route's exit handler clears it)
```

### Files

| Path | Purpose |
|---|---|
| `../utils_pipeline.py`               | Python entry point. Five steps, each gated by its own `--skip-<step>` flag. Emits `{"type":…}` JSON lines on stdout. |
| `../trading_config.py`               | Loads `trading_config.json` at import time so `MIN_PRICE_THRESHOLD`, `MAX_PRICE_THRESHOLD`, `FLOAT_THRESHOLD` come from the same JSON the C++ trader reads. |
| `../get_previous_close.py`           | Step 2 — uses `get_all_symbols()` (no filter). |
| `../get_float.py`                    | Step 3 — uses `get_symbols_by_price()` (price filter only). |
| `../fetch_historycal_data_to_db.py`  | Step 4 — uses `get_symbols_from_database()` (price + float). |
| `../relative_volume_ratio.py`        | Step 5 — same full filter as Step 4. |
| `../clean_db.py`                     | Step 1 — `clear_day_work_tables()`. Includes `HistoryByMin` in the truncate list because Step 4 re-downloads it with a plain INSERT. |
| `app/api/utils/run/route.ts`         | POST — spawn pipeline, stream SSE. Body: `{steps:{…}}`. Refuses concurrent runs (409). Registers child in `lib/pipeline-process`. |
| `app/api/utils/stop/route.ts`        | POST — SIGTERM the active child. 409 if no run is in flight. |
| `app/api/utils/info/route.ts`        | GET — symbol count + table row counts for the panel at the bottom. |
| `app/api/config/route.ts`            | GET / PUT for `../trading_config.json` (atomic write via `.tmp` + rename). |
| `app/utils/page.tsx`                 | The page UI — five step cards each with their own checkbox, run/stop buttons, active-filters banner, editable trading config. |
| `lib/pipeline-process.ts`            | Cross-route singleton holding the active `ChildProcess`. `setActiveChild` / `hasActiveChild` / `killActiveChild`. |

### Five pipeline steps — symbol-selection rules

The five steps are ordered by data dependency: each step needs columns
the previous step populated. **Symbol-selection differs per step**, and
this is the most important contract of the pipeline:

| # | Step       | Python function                                           | Symbol selector                          | Universe              | Writes                      |
|---|---|---|---|---|---|
| 1 | clear      | `clean_db.clear_day_work_tables`                          | n/a                                      | n/a                   | TRUNCATEs day-work tables    |
| 2 | last_price | `get_previous_close.getPreviousClose`                     | `trading_config.get_all_symbols`         | **all** ~2,947         | `Stocks.close`               |
| 3 | float      | `get_float.get_float`                                     | `trading_config.get_symbols_by_price`    | **price-filtered**     | `Stocks.float_value` etc.    |
| 4 | historical | `fetch_historycal_data_to_db.getHistoricalData`           | `trading_config.get_symbols_from_database` | **price + float**    | `HistoryByMin`               |
| 5 | rv         | `relative_volume_ratio.getRelativeVolumeFactor`           | `trading_config.get_symbols_from_database` | **price + float**    | `RelativeVolumeRatioHour`    |

**Why the universes shrink as you go down**:

- Step 2 *cannot* filter by price — that's exactly what it's populating.
  So it walks the whole `Stocks` registry.
- Step 3 has prices but not floats, so it filters by price only. Float
  data takes ~10 minutes via yfinance for 2,947 tickers; running it on
  the price-filtered subset (typically ~400) is the whole point.
- Steps 4 & 5 have both, so they apply the **full** filter from
  `trading_config.json` (`min_price`, `max_price`, `float_threshold`).

**Step 3 count and Step 4 count usually do not match** — and that's
correct, not a bug. Example with `min_price=1, max_price=2,
float_threshold=50,000,000`:

```
412  stocks have  1 ≤ close ≤ 2          ← Step 3 fetches float for all 412
309  of those also have  float < 50M      ← Step 4 processes these
103  have float ≥ 50M                     ← excluded by float filter
  3  have float NULL or 0 (yfinance failed)  ← also excluded
```

If a future step shows MORE rows than the previous step, *that* would
be the bug. The chain is monotonically narrowing.

### `trading_config.json` is the single source of truth

Three readers, one file:

| Reader               | When                                     | How                                                   |
|---|---|---|
| C++ trader            | At process startup                       | `cpp_ultra_low_latency/trading_config.h` reads JSON   |
| Python pipeline       | At `import trading_config` (every run)   | `_load_trading_config_json()` in `trading_config.py`  |
| Dashboard `/utils`    | GET on mount, PUT on Save                | `/api/config` route — atomic `.tmp` + rename          |

Edits in the dashboard's "Trading config (editable)" panel hit
`/api/config` PUT, which writes the JSON. The next pipeline run picks
up the change automatically (Python re-imports per spawn). The C++
trader picks it up on its next `--persist` start.

### Per-step checkboxes — all default ON

The step cards on `/utils` each have a checkbox. All default to ON; the
operator unchecks any step that already ran today (e.g. last_price was
already populated for $1–$5 stocks earlier and the operator just
narrowed the range to $1–$2 — they only need to re-run Step 4 + 5 on
the new subset, since prices and floats are already current).

| Step       | Default | Notes                                                                                                          |
|---|---|---|
| clear      | ON      | Destructive — truncates day-work tables INCLUDING `HistoryByMin` (Step 4 re-downloads). Uncheck to preserve.    |
| last_price | ON      | ~5–10 min for 2,947 tickers via Polygon.                                                                        |
| float      | ON      | ~3–5 min for the price-filtered subset via yfinance (slow, rate-limited).                                       |
| historical | ON      | ~5 min — 5 business days × subset.                                                                              |
| rv         | ON      | < 1 min — pure DB roll-up.                                                                                      |

### Concurrency lock

At most one pipeline runs at a time. The active `ChildProcess` is held
in `lib/pipeline-process.ts` (module-level singleton, not a database
record). A second `POST /api/utils/run` while one is in flight returns
**409**. The Stop endpoint sends SIGTERM; the existing run-route's
exit handler then clears the singleton and the SSE stream closes
naturally.

In dev mode, hot reload reloads the singleton's module and loses the
reference — the spawned process stays alive but becomes unstoppable
from the UI until manually killed (`pkill -f utils_pipeline.py`).
Acceptable for local single-user dev.

### Event protocol

Python emits one JSON event per line on stdout. The route forwards
each verbatim as an SSE `data:` line, plus two synthetic events
(`stderr`, `exit`) it injects itself.

```jsonc
{"type":"start","skip_clear":false}
{"type":"config","min_price":1,"max_price":2,"float_threshold":50000000}

// repeated for each of the 5 steps:
{"type":"step","step":"<name>","status":"running"}
{"type":"progress","step":"<name>","symbol":"NVDA","count":42,"total":2947}
{"type":"step","step":"<name>","status":"complete"}     // or "skipped"

{"type":"done"}

// failure case:
{"type":"error","step":"<name>","message":"…","traceback":"…"}

// route-injected:
{"type":"stderr","message":"…"}
{"type":"exit","code":0,"signal":null}
```

Step keys are exactly: `clear`, `last_price`, `float`, `historical`, `rv`.

### POST body and CLI flag mapping

The dashboard sends `{steps: {clear: bool, last_price: bool, …}}`.
`true` means "run this step", `false` means "skip". The route handler
translates to Python flags:

| Body key      | Flag                  |
|---|---|
| `clear:false`      | `--skip-clear`        |
| `last_price:false` | `--skip-last-price`   |
| `float:false`      | `--skip-float`        |
| `historical:false` | `--skip-historical`   |
| `rv:false`         | `--skip-rv`           |

Skipped steps emit `{"type":"step","step":"<name>","status":"skipped"}`
right at the top of their block — the UI still renders the card with
the SkipForward icon.

### Configuration & Results panel

Two columns at the bottom of the page:

- **Trading config (editable)** — bound to `/api/config`. Every field in
  `trading_config.json` (min_price, max_price, float_threshold,
  relative_volume_factor, increase_from_open_pct, etc.) is editable
  with `Save` / `Reset` buttons. Save calls PUT `/api/config` and
  surfaces "saved · restart C++ trader to apply" — the C++ side only
  re-reads on its next `--persist` start, but the next Python pipeline
  run picks it up instantly.
- **Database status (live row counts)** — fetched from `/api/utils/info`:
  distinct-symbol count from `RelativeVolumeRatioHour`, plus row counts
  for `HistoryByMin`, `RelativeVolumeRatioHour`, `minute_candlesticks`,
  `trades`. Refreshed on page mount and again at the end of each run.

### Active-filters banner

When the pipeline emits `{"type":"config", …}` at startup, the UI
renders a small amber banner above the step cards with the price range
and float threshold currently driving symbol selection:

```
🔻 ACTIVE FILTERS FROM TRADING_CONFIG.JSON   $1.00 ≤ price ≤ $2.00 · float < 50,000,000
```

Lets the operator eyeball-verify that their saved config is the one
this run is using.

## Portfolio page (`/portfolio`)

The only page in the dashboard that renders **two stacked grids on a
single route**, with two different refresh policies — driven by the
operator's distinction between *"what I currently hold"* and *"what
I've already sold this session"*.

```
┌──────────────────────────────────────────────────────────────────┐
│ /portfolio (browser)                                             │
│                                                                  │
│  ┌──────── My Portfolio — IB account positions ───────────────┐  │
│  │  refetchInterval: 5_000   →   GET /api/portfolio           │  │
│  │  Symbol  Position  Avg Cost  Last  %  Account  Snapshot    │  │
│  └────────────────────────────────────────────────────────────┘  │
│                                                                  │
│  ┌──────── Sold positions — session history ──────────────────┐  │
│  │  refetchInterval: false   →   GET /api/portfolio/sold      │  │
│  │  Symbol  Pos  AvgCost  Exit  %  Acct  Snap  SoldAt  Reason │  │
│  └────────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────┘

GET /api/portfolio                                GET /api/portfolio/sold
   │                                                     │
   │ paginatedTableHandler({                             │ paginatedTableHandler({
   │   extraWhere: "sold_at IS NULL",     ←── slice ──→  │   extraWhere: "sold_at IS NOT NULL",
   │   columns: PORTFOLIO_HELD_COLUMNS                   │   columns: PORTFOLIO_SOLD_COLUMNS
   │ })                                                  │ })
   ▼                                                     ▼
SELECT … WHERE sold_at IS NULL                  SELECT … WHERE sold_at IS NOT NULL
   │                                                     │
   │ enrich each row with last_price                     │ (no enrichment — historical)
   ▼
Polygon  GET /v2/snapshot/locale/us/markets/stocks/tickers
            ?tickers=AMS,ATLN,…&apiKey=…
         → response.tickers[i].lastTrade.p
```

### Two routes, one MySQL table

| Route | WHERE | Refresh | Polygon | Use case |
|---|---|---|---|---|
| `/api/portfolio`      | `sold_at IS NULL`      | every 5 s     | yes — `last_price` injected per row | "What am I currently holding and how is it moving?" |
| `/api/portfolio/sold` | `sold_at IS NOT NULL`  | once on mount | no                                  | "Buy-vs-sell post-mortem of this session's exits"   |

The split lives entirely on the dashboard side — the C++ trader still
writes one `Portfolio` table. The dashboard slices it into two views
via the handler's `extraWhere` option (see *URL contract* below).

### `extraWhere` — handler scoping

`paginatedTableHandler` (in `lib/handlers.ts`) accepts an optional
`extraWhere?: string` field. The fragment is `AND`'d into the WHERE
clause built from user filters:

```ts
const fullWhere = opts.extraWhere
  ? (where.sql
      ? `${where.sql} AND (${opts.extraWhere})`
      : ` WHERE (${opts.extraWhere})`)
  : where.sql;
```

This is **trusted** SQL — developer-written, never user input. It's
how the two portfolio routes lock themselves to a slice of the table
without changing the rest of the handler. The `?` parameter / column-
whitelist safety machinery still applies to user filters / sorts on
top of `extraWhere`.

### Polygon enrichment (`lib/polygon.ts`)

`fetchLastTrades(symbols)` makes ONE HTTP call to Polygon's multi-
ticker snapshot endpoint and returns a `Map<symbol, lastPrice>`. The
held route iterates the SQL result rows and injects
`r.last_price = prices.get(r.symbol)`.

| Concern | Behavior |
|---|---|
| API key      | `POLYGON_API_KEY` in `.env.local`, with a hardcoded fallback in `polygon.ts` matching the value used by the Python modules. |
| Rate         | 1 request per 5-s refresh, *regardless of holding count* — the snapshot endpoint accepts a comma-separated ticker list. |
| Failure mode | `fetch` throws → empty map → all `last_price = null`. Cells render blank. No retries, no error surfaced to the user. |
| Latency      | Up to 5 s stale (the polling cycle). Sufficient for "is this going up or down", not for execution decisions. |
| C++ coupling | None. The dashboard opens its own Polygon connection — fully independent of the C++ trader's WebSocket. |

### Held grid — column derivation

| Column                 | Source                               | How                                                         |
|---|---|---|
| `Last`  (`last_price`) | Polygon snapshot (server-side merge) | route handler injects into row before responding             |
| `%`     (`pnl_pct`)    | `(last - avg) / avg * 100`           | computed at render time from the row (`computed` callback)   |

Both are virtual / `computed` — never selected from MySQL, excluded
from sort and filter automatically.

### Sold grid — column derivation

`Exit` (sold price) and `%` (realised P&L) are **parsed from the
`sold_reason` string** the C++ position manager writes. The format is
fixed in `cpp_ultra_low_latency/trade_processor.h`:

```
sold_reason: "STOP_LOSS @ -5.13% (cost=1.5600 tick=1.4800)"
                          │                    │
                          └─→ sold_pct          └─→ sold_price
```

| Column (sold)         | Source        | Parse                          |
|---|---|---|
| `Exit`     (`sold_price`) | `sold_reason` | regex `tick=([0-9.]+)`         |
| `%`        (`sold_pct`)   | `sold_reason` | regex `@\s*([+\-]?\d+\.\d+)%`  |

**Brittleness:** if the C++ format string in the SELL branch changes,
the regexes silently return `null` and the cells render blank. The
full `sold_reason` text stays visible in its own column, so
degradation is graceful — but if a future C++ refactor breaks these,
it will be a silent break.

### Visual decoration (ColumnDef fields used here)

- `trendVsKey: "avg_cost"` on `Last` (held) and `Exit` (sold) → green
  ↑ / red ↓ icon next to the price, comparing against the row's
  `avg_cost`.
- `pctColored: true` on both `%` columns → `+5.00%` emerald,
  `-3.38%` red, `0.00%` muted. Renderer formats the number with sign
  and `%` suffix; valueFormatter is bypassed.
- `rowClassByPrefix` on `sold_reason` → STOP_LOSS rows tint orange,
  TAKE_PROFIT rows tint green (uses `.row-stop-loss` /
  `.row-take-profit` from `globals.css`).

### Why the page does NOT use `TablePage`

`TablePage` assumes one grid per route (it's `h-full` / single-flex).
Two stacked grids on one page need their own layout, so
`app/portfolio/page.tsx` owns the layout directly: a top-level
`overflow-auto` flex column with two `<Section>` sub-components, each
holding its own `useQuery` + `<DataGrid>`. Each grid wrapper has a
fixed height (`h-[28rem]` held, `h-[22rem]` sold) so AG Grid has a
definite parent box to render into.

### Files

| Path | Purpose |
|---|---|
| `app/portfolio/page.tsx`             | Custom 2-section layout — held grid (5-s polling) + sold grid (no polling). |
| `app/api/portfolio/route.ts`         | GET — `extraWhere: "sold_at IS NULL"`. Polygon-enriches each row before returning. |
| `app/api/portfolio/sold/route.ts`    | GET — `extraWhere: "sold_at IS NOT NULL"`. No enrichment. Default sort: `sold_at DESC`. |
| `lib/polygon.ts`                     | `fetchLastTrades(symbols)` — multi-ticker snapshot helper. |
| `lib/tables.ts` → `PORTFOLIO_HELD_COLUMNS` / `PORTFOLIO_SOLD_COLUMNS` | Two distinct column sets + whitelists + default sorts. |

### Hard rules

- **Never modify the C++ to add a price column.** All live / exit
  prices that this page surfaces are derived (Polygon snapshot for
  held, regex parse of `sold_reason` for sold). Adding new MySQL
  columns to `Portfolio` would require a schema migration that the
  C++ trader's startup `TRUNCATE + INSERT` would have to be updated
  to populate — out of scope.
- **Held grid is a 5-s poll, not a WebSocket.** If sub-second freshness
  ever becomes a requirement, see *Known limitations* — a singleton
  Polygon WebSocket inside Next.js is the upgrade path, not a tap of
  the C++ trader's connection (Polygon allows multiple connections per
  account, but coordinating shutdown / hot-reload is the gotcha).
- **Sold grid is one-shot.** Setting `refetchInterval: false` +
  `refetchOnWindowFocus: false` on its `useQuery` is load-bearing —
  the user explicitly asked for a frozen historical view. If a reason
  to "refresh" arises (e.g. a manual reload button), prefer
  invalidating the query key over enabling polling.

## Low Float page (`/low-float`)

The strategy's primary scanner. Reads from the same `Stocks` MySQL
table as `/stocks`, but the route hard-codes the low-float trading
universe via `extraWhere`, and the column set is reordered around the
strategy's signals (Short % first, sorted DESC). Mirrors the legacy
Python `get_low_float_stocks()` helper in `../../get_float.py`.

### Filter

Applied server-side via `paginatedTableHandler`'s `extraWhere`:

```sql
float_value > 0
AND float_value < 10000000              -- LOW_FLOAT_MAX_VALUE constant
AND close >= <min_price>                -- read from trading_config.json
AND close <= <max_price>                -- read from trading_config.json

-- Sanity guards (added 2026-05-03) — defense-in-depth against any
-- corrupted yfinance data still in the registry before the next
-- Step 3 rerun. See `../get_float.py` for the matching write-side
-- gates and the project root CLAUDE.md "Stocks data sourcing" section
-- for the full data-quality story.
AND shares_outstanding > 0
AND float_value <= shares_outstanding   -- Float can never exceed SO
AND (shares_short IS NULL OR
     shares_short <= shares_outstanding * 1.5)
                                        -- 1.5× allows real naked-short
                                        -- outliers like RDGT (Short ≈ SO)
                                        -- but blocks the yfinance bug
                                        -- pattern (Short = 100×–100,000×SO).
                                        -- Keep this threshold in sync with
                                        -- SANITY_MAX_SHORT_TO_SO_RATIO in
                                        -- get_float.py.
```

The route opens `../trading_config.json` on every request and inlines
`min_price` / `max_price` after validating them as finite numbers
(safe to inject — values come from a trusted local file, never from
user input). Edits to the JSON via `/utils → Save` are picked up by
the next refetch — the page polls every 5 s like every other table.

`LOW_FLOAT_MAX_VALUE = 10_000_000` lives both in `lib/tables.ts` (for
the active-filters banner display) and in `app/api/low-float/route.ts`
(for the SQL fragment). Keep the two in sync if the constant ever
moves. It matches `LOW_FLOAT_THRESHOLD` in
`../../trading_config.py` — the C++ trader doesn't read this field
yet, so it's not in `trading_config.json`. Promote it there if/when
C++ adopts it.

### Short % is computed live

The stored `Stocks.short_percent_float` column (yfinance-fed) is
ignored by this page. Instead a virtual alias `short_pct_calc` is
projected via the handler's new `selectExpressions` mechanism:

```sql
(CASE WHEN shares_outstanding > 0
      THEN shares_short / shares_outstanding * 100
      ELSE NULL END) AS `short_pct_calc`
```

`CASE WHEN` guards against divide-by-zero and NULL `shares_outstanding`
(both yield NULL → blank cell). The alias is sortable (MySQL accepts
aliases in ORDER BY) but not filterable (aliases don't work in WHERE —
DataGrid auto-disables the floating filter when `dbExpression` is set
on a ColumnDef). The default sort is `short_pct_calc DESC` so the
most heavily-shorted candidates land on page 1.

`paginatedTableHandler` discovers the expression through
`dbExpressionMap(LOW_FLOAT_COLUMNS)` and emits `(expr) AS \`key\``
in the SELECT projection. See *Computed columns & row highlighting*
above for the full ColumnDef contract.

### Squeeze-candidate flag

`short_pct_calc` carries `highlightAbove: 10, highlightSeverity: "success"`,
so cells with Short % > 10 render in emerald with a `CheckCircle2`
icon. Row tint is intentionally suppressed for `success` severity —
when the operator narrows the universe enough that many rows match,
flooding the table with green stripes adds noise without information.

### Columns

Ordered by relevance to the strategy. Updated 2026-05-04 — added two
cross-validation columns to the right of `Short %`:

| Column                | Type     | Source                                    |
|---|---|---|
| Ticker                | text     | `Stocks.ticker`                           |
| Shares Outstanding    | number   | `Stocks.shares_outstanding`               |
| Float                 | number   | `Stocks.float_value`                      |
| Last Close            | decimal  | `Stocks.close`                            |
| Shares Short          | number   | `Stocks.shares_short`                     |
| Avg Month Volume      | number   | `Stocks.avg_month_volume`                 |
| Short %               | decimal  | `dbExpression` — Yahoo precomputed (see *Short % calculation chain* below) |
| Short % (Finviz)      | decimal  | `Stocks.short_finviz × 100` — populated only when Yahoo > 10 % |
| Short % (SA)          | decimal  | `Stocks.short_stockanalysis × 100` — populated only when Yahoo > 10 % |

The two cross-validation columns are blank for ~95 % of rows by
design — Step 3 only scrapes them when Yahoo's value crosses the 10 %
squeeze-candidate threshold. When all three values agree to within
~1–2 %, the squeeze signal is trustworthy. When Yahoo disagrees with
both Finviz and stockanalysis (the MSAI 111.43 % case — see *Short %
calculation chain*), the operator sees the divergence directly in the
table and can discard the row instead of acting on a yfinance bug.

Note `Stocks.short_percent_float` itself is intentionally NOT surfaced
on this page — the `Short %` column already projects it through
COALESCE. The `/stocks` page still shows the raw column alongside the
two scrape columns for introspection.

### Short % calculation chain

The chain has three layers, evaluated in order. Each row carries the
result of all three and the operator can compare them directly.

1. **Primary — Yahoo's precomputed `shortPercentOfFloat`**

   Stored in `Stocks.short_percent_float` as a fraction in `[0, 1]`
   (DECIMAL(7,6) — see *Schema notes* below). Fetched by Step 3 of the
   pipeline via `yfinance.Ticker(symbol).info["shortPercentOfFloat"]`.
   This is the value Yahoo displays on `finance.yahoo.com/quote/<sym>/
   key-statistics`. Verified 2026-05-04 to match the website to the
   second decimal for VNRX (4.74 %), AIRE (4.58 %), RAYA (8.01 %),
   SKYQ (67.48 %), UGRO (11.03 %).

   The Low Float page projects this through:
   ```sql
   short_percent_float * 100
   ```
   inside a `COALESCE` (next layer is the fallback).

2. **Fallback — manual calc when Yahoo's field is NULL**

   ```sql
   CASE WHEN float_value > 0
        THEN shares_short / float_value * 100
        ELSE NULL END
   ```
   Triggered when yfinance didn't expose `shortPercentOfFloat` for the
   ticker. Both `shares_short` and `float_value` are also yfinance-fed
   (Step 3), so this fallback uses the same source — it just composes
   the ratio at SELECT time. Sanity gates in `../get_float.py` keep
   broken `shares_short` values out (`shares_short <= shares_outstanding
   × 1.5`).

   The full server-side expression is:
   ```sql
   COALESCE(short_percent_float * 100,
            CASE WHEN float_value > 0
                 THEN shares_short / float_value * 100
                 ELSE NULL END)
   ```

3. **Cross-validation — Finviz + stockanalysis (only when Yahoo > 10 %)**

   For squeeze candidates, Step 3 additionally scrapes:

   - **stockanalysis.com** — `https://stockanalysis.com/stocks/<lower>/
     statistics/`, BeautifulSoup parses the `<tr>` containing
     `Short % of Float`. Stored in `Stocks.short_stockanalysis`.
   - **Finviz** — `https://www.finviz.com/quote.ashx?t=<UPPER>`,
     BeautifulSoup parses the `Short Float` cell. Stored in
     `Stocks.short_finviz`.

   Both are stored as fractions in `[0, 1]`. The threshold lives in
   `../get_float.py`:
   ```python
   CROSS_VALIDATE_THRESHOLD = 0.10  # 10%
   ```
   Below threshold → both columns stay NULL → blank cells in the
   dashboard. Above threshold → both helpers fire (one HTTP GET each
   per symbol with a Mozilla User-Agent and a 10-second timeout). On
   typical runs this triggers for ~10 of ~400 price-filtered tickers,
   so the cost is bounded.

#### Why the cross-validation exists — the MSAI bug

Smoke tested on 2026-05-04: yfinance returned
`shortPercentOfFloat = 1.1143` for **MSAI** (= 111.43 %, mathematically
impossible — short interest can't exceed 100 % of float at any rational
broker). Cross-validation flagged it instantly:

| Source                 | Value      |
|---|---|
| yfinance               | 111.43 %   |
| stockanalysis.com      | 8.65 %     |
| Finviz                 | 5.80 %     |
| Polygon Short Interest | (separately confirmed: 100,401 shares short, agrees with truth) |

The pattern surfaced for several other tickers earlier the same day —
yfinance occasionally returns garbage for newly-restructured or
thinly-covered symbols. Without cross-validation, MSAI would have sat
at the top of the squeeze-candidate sort with a fabricated 111 %.

### Schema notes — `Stocks` MySQL table

Updated 2026-05-04. Three changes worth noting for anyone touching the
table from new code:

- `short_percent_float` is `DECIMAL(7,6) NULL` — stores Yahoo's
  fraction in `[0, 1]`. Was previously `INT`, which silently truncated
  yfinance's `0.0801` to `0` and rounded `0.6748` to `1`. Migration
  also nulled 530 historical rows that had been written under the old
  schema with values like `159000000` (interpreted as raw shares short
  at one point during refactoring).
- `short_finviz` — new column, `DECIMAL(7,6) NULL`. Cross-validation
  scrape from Finviz. NULL for rows below the 10 % threshold or where
  the scrape failed.
- `short_stockanalysis` — new column, `DECIMAL(7,6) NULL`. Same shape
  as `short_finviz`, scraped from stockanalysis.com.

The Low Float route's defense-in-depth WHERE clause (see *Filter*
above) still references `shares_short <= shares_outstanding * 1.5` —
this is independent of the cross-validation columns and protects
against any stale yfinance-bug rows still in the registry.

### Data quality caveat

The Short % calc is only as good as the inputs. Some rows in `Stocks`
have `shares_outstanding` values that are clearly broken (a few
thousand shares for tickers that trade millions of shares per day) —
likely yfinance returning a corrupted figure for thinly-covered
tickers. Those rows produce absurd ratios (e.g. 1,490,984 %) and
will sit at the top of the default `short_pct_calc DESC` sort.

We do **not** filter these out automatically. The operator should
spot-check the top of the list and ignore rows where
`shares_outstanding < shares_short` (impossible for a real position).
A `shares_outstanding >= 100_000` floor could be added to `extraWhere`
in the route if the noise becomes a problem.

### Files

| Path | Purpose |
|---|---|
| `app/low-float/page.tsx`               | Custom layout — title + active-filters banner (Float < 10M · price range from JSON) + DataGrid + Pagination. Polls `/api/low-float` every 5 s. |
| `app/api/low-float/route.ts`           | GET — reads `trading_config.json` for the price range, builds `extraWhere`, passes `selectExpressions: dbExpressionMap(LOW_FLOAT_COLUMNS)` to the handler. |
| `lib/tables.ts` → `LOW_FLOAT_COLUMNS`  | Column set, default sort, `LOW_FLOAT_MAX_VALUE` constant, `LOW_FLOAT_TABLE = "Stocks"`. |

### Active-filters banner

Same pattern as `/utils`. Renders an amber strip above the grid:

```
🔻 ACTIVE FILTERS   0 < float < 10,000,000   ·   $1.00 ≤ price ≤ $2.00
                                                                  edit on the Data Pipeline page
```

The page fetches `/api/config` on mount to populate the price range
display. Server-side filtering is independent of this banner — the
banner is purely informational.

## Raw Tape page (`/raw-trades`) — Trades + Quotes downloader

> The route stays `/raw-trades` for URL stability. The page title,
> sidebar label, dialog copy, and section headers were renamed to
> "Raw Tape" on 2026-05-05 when Quotes support was added — the page
> now houses both `RawTrades` AND `RawQuotes` content.

### Two stacked grids on one route

```
┌────────────────────────────────────────────────────────────────┐
│  Raw Tape — Trades & Quotes downloader                          │
│  [Download trades & quotes]  [View chart]  [Clear table]  N rows│
├────────────────────────────────────────────────────────────────┤
│  RAWTRADES + RAWQUOTES                                          │
│                                                                 │
│  ┌──────── Trades grid ───────┐  ┌── Trades summary panel ──┐  │
│  │  ID  Sym  OPEN✓ Price ...  │  │  SYMBOL                  │  │
│  │  ↑   trade ticks (RawTrades)│  │  Open / High / Low /Close│  │
│  │  Activity column shows     │  │  Shares / Short %        │  │
│  │  "Low activity" badge      │  │  RV Baseline (red, bold) │  │
│  │  per row                   │  │  Activity Threshold      │  │
│  │                            │  └──────────────────────────┘  │
│  │                            │                                │
│  └────────────────────────────┘                                │
│  Pagination + page-size selector                                │
│                                                                 │
│  ─── scroll the page ───                                        │
│                                                                 │
│  ┌──────── Quotes grid ───────┐  ┌── Quotes summary panel ──┐  │
│  │  ID  Sym  Bid  Bid sz  ... │  │  SYMBOL                  │  │
│  │  ↑   NBBO snapshots         │  │  Worst spread (max)      │  │
│  │  (RawQuotes)               │  │  Best  spread (min)      │  │
│  │                            │  │  Average spread (red>10c)│  │
│  │                            │  │  Quotes shown / total    │  │
│  └────────────────────────────┘  └──────────────────────────┘  │
│  Pagination                                                     │
└────────────────────────────────────────────────────────────────┘
```

### How it's wired

| Concern | File / mechanism |
|---|---|
| Page composition | `app/raw-trades/page.tsx` — `<TablePage>` for the trades half + `<QuotesSection>` passed as `bottomPanel`. Both halves visible via vertical scroll on the page wrapper |
| Trades grid + side panel | `TablePage` props `columns={RAW_TRADES_COLUMNS}`, `renderSidePanel={(rows) => <SummaryPanel rows={rows} rules={rules} />}` |
| Quotes grid + side panel | Custom `<QuotesSection>` inlined in the same file. Two-column inner layout (`xl:grid-cols-[1fr_320px]`) — grid on the left, `<QuotesSummaryPanel>` on the right |
| Trades data | `GET /api/raw-trades` (paginated table handler) |
| Quotes data | `GET /api/raw-quotes` (paginated table handler — added 2026-05-05) |
| Clear button | `POST /api/raw-trades/clear` — TRUNCATEs **both** RawTrades and RawQuotes. Dialog title says `Clear RawTrades + RawQuotes?`. Endpoint name kept for stability |
| Download | `<DownloadTradesDialog apiPath="/api/raw-trades/run">`. Single click pulls trades + quotes for the selected (year, month, day, hour, minute, symbol). Four step-rows in the dialog: download trades, save trades, download quotes, save quotes |

### Trades grid — special columns and decorations

The trades grid uses `RAW_TRADES_COLUMNS` from `lib/tables.ts`. Two
decorations come from the page (not the column definitions):

| Decoration | Where it comes from | What you see |
|---|---|---|
| Green row tint on OHLC-determining ticks | `getRowClass` in `raw-trades/page.tsx`, runs `rows__ohlc__cache(allRows, rules)` per render | Rows that set OPEN, CLOSE, HIGH, or LOW are tinted emerald |
| `OPEN ✓` badge inside the Price cell of the row whose tick set the open | `getCellPrefix` callback when `columnKey === "close"` and `ohlc.openId === row.id` | Bold emerald `OPEN` + check-circle icon prepended to the price value |
| `Low activity` badge inside the Activity column | `getCellPrefix` callback when `columnKey === "_activity_status"` and the row is in `ohlc.lowActivityIds` | Bold amber `Low activity` text |

The OHLC walker (`computeOhlcFromRows`) replicates C++
`trade_processor.h::update_ohlcv` Block 0 + Block 1, gated by
`condition_allows`. The activity walker maintains a running
`activeSeconds: Set<number>` and per row evaluates
`active > sec × lowActivityThreshold` — the same math as
C++ `passes_activity_check` (post the 2026-05-05 fix that anchors
elapsed at second 0 of the minute, matching the Python original).

### Trades summary panel (`SummaryPanel`)

Renders right of the trades grid (320 px column at xl breakpoint).
Header card with the symbol, then:

| Block | Content |
|---|---|
| OHLC (top) | Open / High / Low / Close — recomputed client-side from the rows currently shown using the same gates the C++ trader applies |
| Stocks data (middle, separated by border) | Shares Outstanding · Short % (from `/api/stocks` for this symbol) |
| RV Baseline | `RelativeVolumeRatioHour` row for this symbol's (hour, AM/PM) bucket. Rendered **bold + red** to make the figure pop against the rest of the panel |
| Activity Threshold | The `low_activity_threshold` value from `trading_config.json`, formatted as a percentage (e.g. `33 %`). Comes from `/api/raw-trades/ohlc-rules`. Lets the operator see exactly what % distribution the activity check was looking for |
| Footer | "Selection rules" `<details>` block — shows the C++ OHLC rules exactly so the operator can cross-check |

### Quotes section (`QuotesSection` + `QuotesSummaryPanel`)

Independent React Query (`/api/raw-quotes`), independent filters /
sort / pagination state. Refetches every 5 s like every other table.

The summary panel has:

| Field | Computed how |
|---|---|
| Worst spread (max) | `Math.max(spreads)` across the rows currently shown |
| Best spread (min) | `Math.min(spreads)` — can be negative for crossed-market events |
| Average spread | Arithmetic mean. **Red + bold** when `> $0.10`, signalling a wide-spread regime (~3 % of price for a $3 stock = MMs retreating) |
| Quotes shown | Row count on this page |
| Quotes total | Total rows in the table for the active query |

Negative spreads (rare) are kept in the calc — they're real microstructure events worth surfacing.

### `/api/raw-trades/ohlc-rules`

Endpoint that drives the dashboard's client-side OHLC + activity
walkers. Reads two files:

- `../trading_config.json` →
  - `min_trade_size` (default 100) — for the size gate
  - `low_activity_threshold` (default 0.33) — for the per-row Low activity badge
- `../polygon_conditions_trade_stocks.csv` →
  - per-condition `(updates_open_close, updates_high_low, updates_volume)` triples

Returned shape:

```json
{
  "minTradeSize": 100,
  "lowActivityThreshold": 0.33,
  "conditions": {
    "1":  { "oc": true,  "hl": true,  "vol": true  },
    "12": { "oc": true,  "hl": false, "vol": true  },
    "37": { "oc": false, "hl": false, "vol": true  },
    ...
  }
}
```

Cached for 5 minutes on the client (`staleTime`) — config changes
rarely.

### Quotes columns (`RAW_QUOTES_COLUMNS`)

Defined in `lib/tables.ts`. Order: `ID`, `Symbol`, `Bid`, `Bid sz`,
`Ask`, `Ask sz`, `Spread`, `Time`, `Bid ex`, `Ask ex`, `Cond`, `Tape`.

`spread` is computed by the Python download script on insert (`ask
- bid`), not by Polygon. Negative values can appear for crossed
markets and are kept rather than clamped.

### Trade-Quotes pipeline (`download_trades_pipeline.py`)

The single Python entrypoint emits 4 step events instead of the old
2: `download_trades` → `save_trades` → `download_quotes` →
`save_quotes`. The dashboard `DownloadTradesDialog` renders all four
as live progress rows. The `done` event reports both
`trades_saved` and `quotes_saved` counts; the legacy `saved` field
is still recognised for backward compatibility. If the quotes
download fails after trades are persisted, the script emits `done`
with `quotes_saved=0` rather than rolling back trades — partial
data is more useful than none.

## Adding a new table page

1. Add the table to `src/lib/tables.ts`:
   ```ts
   export const FOO_TABLE = "foo_table";
   export const FOO_COLUMNS: ColumnDef[] = [
     { key: "id",        label: "ID",   type: "number" },
     { key: "timestamp", label: "Time", type: "datetime_ms" },
     { key: "symbol",    label: "Sym",  type: "text" },
     // …
   ];
   // Use dbColumnKeys() so the whitelist excludes any computed columns.
   export const FOO_COLUMN_WHITELIST = new Set(dbColumnKeys(FOO_COLUMNS));
   export const FOO_DEFAULT_SORT = { column: "id", dir: "desc" as const };
   ```

2. Create `src/app/api/foo/route.ts`:
   ```ts
   import { paginatedTableHandler } from "@/lib/handlers";
   import { FOO_TABLE, FOO_COLUMNS, FOO_COLUMN_WHITELIST, FOO_DEFAULT_SORT, dbColumnKeys } from "@/lib/tables";
   export const GET = (req: Request) =>
     paginatedTableHandler(req, {
       table: FOO_TABLE,
       columnList: dbColumnKeys(FOO_COLUMNS),   // skips `computed` cols
       columnWhitelist: FOO_COLUMN_WHITELIST,
       defaultSort: FOO_DEFAULT_SORT,
     });
   ```

3. Create `src/app/foo/page.tsx`:
   ```tsx
   "use client";
   import { TablePage } from "@/components/TablePage";
   import { FOO_COLUMNS } from "@/lib/tables";
   export default function FooPage() {
     return (
       <TablePage
         title="Foo"
         description="foo_table"
         apiPath="/api/foo"
         columns={FOO_COLUMNS}
         chartTitle="Top symbols on this page"
       />
     );
   }
   ```

4. Add `{ href: "/foo", label: "Foo" }` to `NAV_ITEMS` in
   `src/components/Sidebar.tsx`.

That's it — filters, pagination, sorting, dark grid, auto-refresh, and the
top-symbols chart all come for free.

## Theme & visual conventions

This UI follows the **premium-ui design system** (see
`/Users/tan/.claude/skills/premium-ui/`). Both light and dark modes are
first-class — every surface, border, shadow, and accent is dual-spec.

### Theme toggle

- **Light is the default.** The user switches to dark via the sun/moon
  button in the header (`src/components/ThemeToggle.tsx`).
- State lives in `ThemeProvider` (`src/components/ThemeProvider.tsx`)
  and is persisted to `localStorage` under the key `td.theme`.
- On first paint we always render light to avoid hydration mismatch;
  the stored preference is re-applied in a `useEffect` on mount.
- `ThemeProvider.setTheme()` adds/removes the `.dark` class on `<html>`.
  Every Tailwind class in the app reads from `dark:` variants — there is
  no JS-controlled stylesheet swap.

### Page wrapper

```
bg-gradient-to-b from-stone-50 via-white to-stone-50
dark:from-zinc-950 dark:via-zinc-900 dark:to-zinc-950
```

Set on the inner `<div>` in `app/layout.tsx`.

### Surfaces & borders

| Element | Light | Dark |
|---|---|---|
| Glass card | `bg-zinc-900/[0.03]` | `bg-white/[0.03]` |
| Glass card hover | `bg-zinc-900/[0.05]` | `bg-white/[0.06]` |
| Card border | `border-zinc-900/5` | `border-white/5` |
| Card border hover | `border-zinc-900/10` | `border-white/10` |
| Sidebar surface | `bg-white/40` (with backdrop-blur) | `bg-zinc-950/40` |
| Sticky header | `bg-white/70` (with backdrop-blur) | `bg-zinc-950/70` |
| Card radius | `rounded-2xl` | same |
| Input/button radius | `rounded-xl` | same |
| Pill / chip radius | `rounded-full` | same |

### Accent — amber/orange

| Use | Class |
|---|---|
| Active nav highlight, filter chips, page-N badge | `bg-amber-500/10 border-amber-500/20 text-amber-700 dark:text-amber-300` |
| Icon container | `bg-amber-500/10 border-amber-500/20` with `text-amber-600 dark:text-amber-400` icon |
| Primary button (gradient) | `bg-gradient-to-r from-amber-500 to-orange-500 text-black` |
| Section divider underline | `bg-gradient-to-r from-amber-400 to-orange-500` (used as a 0.5px-tall, 16-wide bar under page titles) |
| Chart bars | linear gradient `#fbbf24 → #f97316` (defined inline in `SymbolBarChart`) |
| Row hover (AG Grid) | `rgba(245,158,11,0.06)` light · `rgba(245,158,11,0.08)` dark |

### Typography

- Page title: `text-3xl font-bold tracking-tight`
- Eyebrow above title: `text-[11px] uppercase tracking-[0.22em] text-zinc-500`
- Tabular numbers everywhere: `font-mono tabular-nums`
- Geist Sans + Geist Mono only — set up in `app/layout.tsx`.

### Animations

- Page entrance: `animation: fadeSlideUp 0.6s ease-out both` (keyframe in
  `globals.css`). Stagger child elements with `animationDelay` of
  `${index * 80}ms`.
- Hover lift on tiles: `hover:-translate-y-1` over 500 ms
- Active button press: `active:scale-[0.97]`
- Theme toggle press: `active:scale-95`

### AG Grid themes

Two `themeQuartz` configs in `DataGrid.tsx`:
- `lightTheme` — transparent surface, `#18181b` text, amber row hover at 6 % opacity
- `darkTheme`  — transparent surface, `#fafafa` text, amber row hover at 8 % opacity

Both inherit the page's font via `--font-sans`. The transparent surface
lets the table sit cleanly inside its glass card.

### Icons

`lucide-react` exclusively. `size-4` inline, `size-5` inside icon
containers. Imports used so far: `LayoutDashboard`, `Activity`,
`ListOrdered`, `Sun`, `Moon`, `BarChart3`, `Filter`, `Plus`, `X`,
`ChevronFirst`, `ChevronLast`, `ChevronLeft`, `ChevronRight`,
`ArrowRight`, `RefreshCw`, `Loader2`.

## DB connection

| Setting | Value |
|---|---|
| Host | `localhost` |
| Port | `3306` |
| User | `root` |
| Database | `histFinanData` |
| Password | hardcoded in `lib/db.ts` (dotenv mangles `$`) |
| Pool size | 5 connections |

The pool is **lazy** — created on first `getPool()` call so dev hot-reload
doesn't leak pools. Module load is cheap.

## Performance notes

| Concern | Solution |
|---|---|
| 1M-row table | Never load all of it — server-side pagination, 100 rows per page |
| `COUNT(*)` over filtered 1M rows | Currently runs every page change. Will need an upper-bound cap (e.g. `LIMIT 10000`) once we hit a million-row table |
| Slow filters | Required: indexes on `symbol`, `timestamp`, `status`. Run `SHOW INDEX FROM <table>` if a filter feels slow |
| Re-fetch on every keystroke | `FilterBar` updates state only on Add/Enter, not per-keystroke |

## Auto-refresh

Every TanStack Query in the app uses `refetchInterval: 5000`. So:

- Header counts refresh every 5 s
- Overview tiles refresh every 5 s
- Active table page (Signals or Orders) refetches its current page every 5 s

Switching pages does NOT refetch the previous one (TanStack Query parks
the previous query). When you return, you see cached data instantly while
a fresh fetch is in flight.

## Known limitations / deferred decisions

- AG Grid Community lacks server-side row model (Enterprise license only).
  We use client-side row model + manual page controls — works fine for
  any table size since we only ship one page at a time.
- No login. If we ever expose this beyond localhost, we add NextAuth and
  swap the hardcoded DB creds for a secret.
- No real-time push. Polling is enough for "post-analysis the majority of
  the time" use case. WebSocket can be added later if a live tile needs
  millisecond freshness.
- No write paths. The dashboard never INSERTs / UPDATEs anything.
  Persistence into MySQL is exclusively the C++ persister thread's job.

## Quick import reference

```ts
import { Button } from "@/components/ui/button";
import { Card, CardHeader, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Select, SelectTrigger, SelectContent, SelectItem, SelectValue } from "@/components/ui/select";

import { useQuery, keepPreviousData } from "@tanstack/react-query";
import { BarChart, Bar, XAxis, YAxis, Tooltip, CartesianGrid, ResponsiveContainer } from "recharts";

import { getPool, query, count, execute } from "@/lib/db";
import { buildWhere, buildOrderBy, buildLimit, parseFiltersParam, parseSortParam } from "@/lib/query-builder";
import type { Filter, SortDir } from "@/lib/query-builder";
import { paginatedTableHandler } from "@/lib/handlers";
import {
  SIGNALS_COLUMNS, ORDERS_COLUMNS, STOCKS_COLUMNS, RV_COLUMNS,
  dbColumnKeys,
} from "@/lib/tables";
import { formatterFor, formatTimestampSeconds } from "@/lib/format";

import { TablePage } from "@/components/TablePage";
import { DataGrid, type RowAction } from "@/components/DataGrid";
import { Pagination } from "@/components/Pagination";
import { SymbolBarChart } from "@/components/SymbolBarChart";
import { ThemeProvider, useTheme } from "@/components/ThemeProvider";
import { ThemeToggle } from "@/components/ThemeToggle";
import { ConfirmDialog } from "@/components/ConfirmDialog";
import { AddStockDialog } from "@/components/AddStockDialog";
import { RowDeleteButton } from "@/components/RowDeleteButton";
```
