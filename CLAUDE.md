# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Stock trading system that monitors real-time market data via Polygon.io WebSocket, generates trade signals, and executes orders through Interactive Brokers (IB Gateway). Built for day trading low-float, small-cap stocks with relative volume analysis.

## Key Architecture

### Data Flow
1. **Pre-market data pipeline** (`run_data_processing.sh`): Fetches historical minute-bar data, float values, previous closes, and computes relative volume ratios -- all stored in MySQL
2. **Real-time WebSocket consumer** (`multiprocessing_websocket_rv_hour_AI.py`): Main production entry point. Connects to Polygon.io WebSocket for live trade/quote data, processes signals using multiprocessing, persists trade signals to MySQL
3. **Position management** (`position_manager.py`, `real_time_position_manager.py`): Monitors open positions via IB, handles stop-loss alerts and profit-taking. `position_manager.py` uses SQLite; `real_time_position_manager.py` uses MySQL and is imported by the websocket processes
4. **Scheduled launcher** (`programmed_task.py`): Uses `schedule` to auto-start `mainT()` from the main websocket module at a configured time daily

### Databases
- **MySQL** (`histFinanData` on localhost:3306): Primary production database. Stores Stocks, HistoryByMin, trades, Orders, TradeSignalsBuyPerSecond, RelativeVolumeRatioHour, and other runtime tables
- **SQLite** (`histFinanData.db`): Legacy/fallback database with similar schema. Some modules still use it (position_manager.py, clean_day_data.py, experiments.py)
- Full schema definition: `db_definition.txt`
- `mysql_test.py` contains `transfer_data_to_mysql()` for migrating SQLite Stocks data to MySQL

### Database Tables (Summary)

| Table | Purpose | Updated by | Lifecycle |
|-------|---------|------------|-----------|
| **Stocks** | Master symbol registry (float, shares_outstanding, prev_close) | `get_float.py`, `get_previous_close.py` | Persistent |
| **HistoryByMin** | Historical minute-bar OHLCV | `fetch_historycal_data_to_db.py` | Persistent |
| **HistoryByMinToday** | Current session minute bars | WebSocket consumer | Daily reset |
| **TradeSignalsBuyPerSecond** | All trade signal triggers (before validation) | `trade_signal_persist_process` | Persistent |
| **Orders** | Order execution audit trail (Processing/Filled/Not executed) | `trade_signal_consumer` (4 workers) | Persistent |
| **trades** | Raw tick-level trades (only signaled symbols) | `consumer_process` at minute rollover | Daily reset |
| **minute_candlesticks** | Per-minute OHLCV for all symbols | `consolidate_minute_task` | Daily reset |
| **RelativeVolumeRatioHour** | **PRIMARY** hourly relative volume factors | `relative_volume_ratio.py` | Persistent |
| **RelativeVolumeRatio** | Legacy relative volume factors | `relative_volume_ratio.py` | Persistent |
| **QueueBehavior** | Queue health and processing latency metrics | `consumer_process` | Persistent |
| **RawTrades** | Downloaded historical trades from Polygon.io | `experimental_dashboard.py` | Manual |

Daily reset tables are cleared by `clean_db.py`.

**Connection Pattern:**
```python
db_connection = mysql.connector.connect(
    host="localhost",
    port=3306,
    user="root",
    password="E_I$S5PFri",
    database="histFinanData"
)
```

### External APIs & Services
- **Polygon.io**: REST API (via `polygon` Python client) for historical aggregates, previous close, news. WebSocket for real-time trades (`T.*`) and quotes (`Q.*`)
- **Interactive Brokers**: Via `ib_insync` library. TWS Paper Trading on port 7497, IB Gateway Docker on ports 4001 (live) / 4002 (paper). Use `ib.portfolio()` for positions (NOT `ib.positions()`)
- **Yahoo Finance**: `yfinance` used in `get_float.py` for float/shares outstanding data
- **News sources**: Polygon news, Benzinga, Finnhub, GlobeNewsWire, PR Newswire -- each has its own module

### Key Modules
- `trading_config.py` -- **centralized configuration**: symbol selection criteria, trading thresholds, all processes MUST use `get_symbols_from_database(mysql_cursor)` for consistent symbol lists
- `get_float.py` -- fetches float values and shares outstanding per ticker
- `get_previous_close.py` -- updates stock close prices from Polygon REST API
- `relative_volume_ratio.py` -- computes relative volume factor from historical minute bars
- `fetch_historycal_data_to_db.py` -- loads historical minute-bar data into DB
- `clean_db.py` -- functions to clear all tables, day-work tables, or intraday tables (both SQLite and MySQL variants)
- `real_time_position_manager.py` -- MySQL-based position monitoring with stop-loss/take-profit, imported by websocket processes
- `aggregates_per_second.py` -- per-second aggregate processing with `numba` JIT optimization
- `trade_signals_query.py` -- displays trade signals with formatted output (colorama/tabulate)
- `select_table.py` -- displays table row counts and data summaries

### TUI Dashboards (Textual Framework)

Three independent terminal dashboards:

1. **`ui_experiments.py`** (`./run_dashboard.sh`) -- Real-time trading dashboard with live WebSocket data, IB portfolio positions via `ib.portfolio()`, and manual "Buy Stock" button
2. **`utils_dashboard.py`** (`./run_utils.sh`) -- Pre-market data pipeline with progress tracking for each data loading step
3. **`experimental_dashboard.py`** (`./run_experimental.sh`) -- Testing workspace: download historical trades from Polygon.io, preview RawTrades table, 3-step pipeline progress

**Threading pattern for non-blocking UI** (critical -- never use `run_worker().on_complete()`):
```python
def on_button_pressed(self, event):
    def worker():
        result = slow_operation()
        def update_ui():
            self.notify(f"Complete: {result}")
        self.app.call_from_thread(update_ui)
    threading.Thread(target=worker, daemon=True).start()
```

### Multiprocessing Variants
Several variants of the websocket consumer exist, reflecting iterative development:
- `multiprocessing_websocket.py` -- base version
- `multiprocessing_websocket_rv_hour_AI.py` -- **current production version** with hourly relative volume and dashboard integration
- `multiprocessing_websocket_rv_hour_second.py` -- per-second variant
- `multiprocessing_websocket_rv_hour_multi_consumer.py` -- multi-consumer variant

## Technical Deep Dive: `multiprocessing_websocket_rv_hour_second.py`

This is the **per-second aggregate variant**. It subscribes to Polygon.io `A.*` channels (per-second aggregate bars) instead of `T.*` (raw trades), and spawns 12 processes (vs 8 in production).

### Per-Second Aggregates vs Raw Trades

The key difference is the WebSocket subscription prefix in `create_subscription_list()`:
```python
# This file (per-second):
subscriptions = [f"A.{ticker}" for ticker in tickers]   # Aggregate bars

# Production (rv_hour_AI):
subscriptions = [f"T.{ticker}" for ticker in tickers]   # Raw trades
```

Aggregate bar messages have different fields than raw trade messages:
| Field | Per-Second Aggregate (`A.*`) | Raw Trade (`T.*`) |
|-------|----------------------------|-------------------|
| Price | `m.open`, `m.close`, `m.high`, `m.low` | `m.price` |
| Size | `m.volume` (total bar volume) | `m.size` (individual trade size) |
| Time | `m.end_timestamp` | `m.timestamp` |
| Metadata | N/A | `m.conditions`, `m.id`, `m.exchange`, `m.trf_id` |

Because aggregates lack trade-level metadata, the `consumer_process` hardcodes placeholders:
```python
trade_id = "trade_id"           # Not available in aggregates
trade_exchange = "exchange"     # Not available in aggregates
trade_trf_id = "trade_trf_id"  # Not available in aggregates
```

And OHLCV condition filtering (`condition_affects_ohlcv_component`) is disabled/commented out since aggregates don't carry trade conditions.

### Process Architecture (12 Processes)

```
main() -> run_processes() -> multiprocessing.Manager()

P1:  market_data_producer         WebSocket(A.*) -> trade_queue [100K]
P2:  consumer_process             trade_queue -> OHLCV + signal generation
P3-6:  trade_signal_consumer (4x)   trade_signal_queue [100K] -> IB orders
P7-10: news_catalyst_analyzer (4x)  news_queue [100K] -> IB reqHistoricalNews
P11: sell_off_process             selloff_queue [100] -> stop-loss execution
P12: take_profits_process         take_profit_queue [100] -> profit taking
```

### Queues (5 Multiprocessing Queues)

| Queue | Capacity | Producer | Consumer(s) | Purpose |
|-------|----------|----------|-------------|---------|
| `trade_queue` | 100,000 | `market_data_producer` | 1x `consumer_process` | Raw per-second aggregate messages |
| `trade_signal_queue` | 100,000 | `consumer_process` | 4x `trade_signal_consumer` | Validated BUY signals for order execution |
| `news_queue` | 100,000 | `consumer_process` | 4x `news_catalyst_analyzer` | Symbols needing IB news lookup |
| `selloff_queue` | 100 | `consumer_process` | 1x `sell_off_process` | Stop-loss alerts (price < entry * 0.95) |
| `take_profit_queue` | 100 | `consumer_process` | 1x `take_profits_process` | Take-profit alerts (price >= entry * 1.10) |

### Shared State

Only **one** managed dict via `multiprocessing.Manager()`:
```python
real_time_positions = manager.dict()  # symbol -> avg_cost
```

Production version manages 4 dicts (positions, signals, volume, activity). The `trade_signals_track_stock_price` dict is a regular `{}` (not managed), so mutations in `consumer_process` are invisible to `trade_signal_consumer` processes -- this is a known bug.

### Differences from Production (`multiprocessing_websocket_rv_hour_AI.py`)

| Aspect | Per-Second Variant | Production |
|--------|-------------------|------------|
| WebSocket subscription | `A.*` (per-second aggregates) | `T.*` (raw trades) |
| Total processes | 12 | 8 |
| News pipeline | 4 dedicated `news_catalyst_analyzer` processes | None |
| DB host | AWS RDS (`database-trading.cut2mkgg2cz9.us-east-1.rds.amazonaws.com`) | localhost |
| DB user | `admin` | `root` |
| Trade signal persistence | Inline in `consumer_process` | Dedicated `trade_signal_persist_process` |
| Minute candlestick writes | Inline in `consumer_process` | Dedicated `consolidate_minute_task` |
| Managed dicts | 1 (`real_time_positions`) | 4 (positions, signals, volume, activity) |
| Trade condition filtering | Disabled | Active via CSV lookup |
| Spread check in order validation | Missing | $0.20 max |
| IB main client ID | 9 | 0 |

### Unused Async Architecture

The file contains a second, **unused** architecture based on `asyncio.gather()` (lines 1646-1753) with `asyncio.Queue` and `aiosqlite`. The entry point `asyncio.run(run_trading_strategy())` is commented out on line 1753. This suggests the file was originally async before being migrated to multiprocessing.

## Running

```bash
# Activate virtual environment
source myenv/bin/activate

# Pre-market data pipeline (run before market open)
./run_data_processing.sh

# Start the main websocket trading system
python3 multiprocessing_websocket_rv_hour_AI.py

# Or use the scheduled launcher
python3 programmed_task.py

# Start IB Gateway (Docker)
docker-compose up -d

# Time sync (keeps system clock accurate)
./time.sh

# TUI Dashboards
./run_dashboard.sh        # Real-time trading
./run_utils.sh            # Data pipeline
./run_experimental.sh     # Testing workspace
```

## Technical Deep Dive: `multiprocessing_websocket_rv_hour_AI.py`

### Architecture Pattern
Multi-stage pipeline using **multiprocessing.Manager** for shared state across 8 independent processes:

**Process Pipeline:**
1. **market_data_producer** -> WebSocket client receives real-time trades from Polygon.io, pushes to `trade_queue` (10K capacity)
2. **consumer_process** -> Consumes trades, computes per-minute OHLCV, calculates relative volume, generates trade signals -> pushes to `trade_signal_queue` + `trade_signal_persist_queue`
3. **trade_signal_consumer (4 workers)** -> Validates signals through 7-step filter, executes IB limit orders (IB client IDs 25-28)
4. **trade_signal_persist_process** -> Persists signals to MySQL `TradeSignalsBuyPerSecond` table
5. **consolidate_minute_task** -> Saves per-minute candlesticks to MySQL at minute rollover

### Shared State via multiprocessing.Manager
```python
real_time_positions = manager.dict()           # Tracks open positions (symbol -> avg_cost)
trade_signals_to_buy = manager.dict()          # Prevents duplicate signals
trade_consumer_volume_map = manager.dict()     # Per-symbol cumulative volume
activity_second_count_hashmap = manager.dict() # Unique seconds with trades (anti-pop-and-drop)
```

### Trade Signal Generation Logic
**Trigger conditions (all must be met):**
1. `relative_volume_factor_hour >= RELATIVE_VOLUME_FACTOR` (configurable in `trading_config.py`)
2. `close > open` (bullish candle)
3. `(close - open) / open * 100 >= INCREASE_FROM_OPEN` (minimum price increase)
4. `record_count < TRADE_SIGNAL_LIMIT` (max signals per symbol)
5. No existing BUY signal for symbol
6. No filled BUY order for symbol

**Special signal types:**
- **Short squeeze**: High short-interest stocks (>5%) with `price_change > 4%`
- **Price tracking**: Stocks that fail initial check but are tracked for future increases
- **Low activity recovery**: Stocks with `active_seconds < 40%` threshold are re-evaluated

### Order Execution Validation (7-Step Filter)
Runs at second 55 of each minute, validates in sequence (any failure -> abort):

| Step | Check | Threshold | Reason |
|------|-------|-----------|--------|
| 1 | Low activity | 40% of elapsed seconds must have trades | Prevent "pop and drop" |
| 2 | Volume freshness | Current volume > 3x last 10-min avg | Avoid stale volume spikes |
| 3 | Spread | Max $0.20 | Limit slippage risk |
| 4 | Price range | `MIN_PRICE_THRESHOLD` - `MAX_PRICE_THRESHOLD` | Configuration bounds |
| 5 | Bullish candle | `price > open` | Only buy uptrends |
| 6 | Momentum | Price increase >= `INCREASE_FROM_OPEN`% from open | Validate strength |
| 7 | Spike risk | Price increase < `PRICE_SPIKE_RISK_THRESHOLD`% from open | Avoid parabolic moves |

**Order placement:**
- Limit order at `ask_price + $0.02` (aggressive fill)
- IB connection: Random client ID (200-1000) to avoid conflicts
- Fill timeout: 10 seconds -> auto-cancel
- Price protection: Cancel if ask increases during fill

### Real-Time Risk Management
Monitored on **every incoming trade** in `consumer_process`:
- **Stop-loss**: Drop below `MAX_LOSS_TOLERANCE_PER_TRADE` of entry -> triggers `selloff_queue`
- **Take-profit**: 5% gain from entry -> triggers `take_profit_queue`
- Position tracking via `real_time_positions` shared dict

### Per-Minute State Reset
At minute rollover (`current_minute != datetime.now().minute`):
1. Clears all OHLCV maps, volume counters, activity sets
2. Reloads `RelativeVolumeRatioHour` from MySQL for current hour/AM-PM
3. Pushes consolidated data to `consolidate_minute_queue`
4. Saves raw trades to MySQL `trades` table (only for symbols with signals)
5. Inserts per-symbol volume/close to `minute_candlesticks` table

### WebSocket Details
- **Library**: `polygon.WebSocketClient` from official SDK
- **Subscription format**: `["T.AAPL", "T.TSLA", ...]` (trade streams only)
- **Message handler**: Zero-processing design -- immediate `queue.put()` for max throughput
- **Timestamp precision**: Milliseconds (Unix epoch)
- **Trade conditions**: Filtered via `polygon_conditions_trade_stocks.csv` lookup to determine OHLCV impact

### Configuration
All trading parameters are centralized in `trading_config.py`. Key values include price range, float thresholds, relative volume factors, trade capital, stop-loss tolerance, and signal limits. Always reference `trading_config.py` for current values -- do not hardcode thresholds elsewhere.

### Known Limitations
1. **Single consumer bottleneck**: Only one `consumer_process` handles all trade queue messages
2. **No WebSocket reconnection**: System stops if connection drops
3. **Memory growth**: `trades_by_symbol` dict grows until minute rollover (OOM risk on extreme volume)
4. **Hardcoded API keys**: Security risk
5. **No connection pooling**: Each process creates own MySQL connection

## Stocks data sourcing — hybrid Polygon + yfinance (implemented 2026-05-03)

> Previous "Planned improvement" section content moved here as the
> historical record after the migration was implemented. Search for
> "LEGACY (pre-2026-05-03)" inside `get_float.py` to see the original
> yfinance-only loop preserved as a comment block for rollback.

### Current state

| Field | Source today | Why |
|---|---|---|
| `Stocks.shares_outstanding` | **Polygon** Ticker Overview (`weighted_shares_outstanding`) | yfinance was wrong for ~30 % of rows (ADRs, post-reverse-split tickers). Polygon's weighted figure handles multi-class shares correctly. |
| `Stocks.shares_short`        | **Polygon** Short Interest API (latest FINRA settlement) | yfinance was wrong for ~27 % of rows. Polygon ingests the FINRA bi-monthly file directly. |
| `Stocks.float_value`         | **yfinance** `floatShares` only                | Polygon does NOT expose float. Schwab Trader API has `marketCapFloat` but the dev-app approval is pending — see "Pending: Schwab" below. |
| `Stocks.short_percent_float` | **NULL** (column no longer written)            | Vestigial. The dashboard computes Short % live in SQL via `shares_short / shares_outstanding × 100` — no need for a stored value. |

### How it runs end-to-end

When the operator clicks **Load data for trading** on `/utils`, Step 3
("Float → Stocks.float_value") triggers `utils_pipeline.py` →
`get_float.get_float()`, which:

```
for each symbol in price-filtered subset (~400 tickers):
    SO     = polygon_shares_outstanding(symbol)   # GET /v3/reference/tickers/{sym}
    Short  = polygon_short_interest(symbol)       # GET /stocks/v1/short-interest?sort=settlement_date.desc&limit=1
    Float  = yfinance.Ticker(symbol).info["floatShares"]

    apply sanity gates:
      if Float > SO:              → drop Float (NULL)
      if Short > 1.5 × SO:        → drop Short (NULL)

    UPDATE Stocks SET shares_outstanding=…, shares_short=…, float_value=…, short_percent_float=NULL
    WHERE ticker = symbol

    # any field that came back None gets explicitly NULLed so stale
    # values from previous runs are cleaned out

print [SANITY SUMMARY] N broken floats / M broken shorts dropped
```

Logs:
- Per-symbol prints (SO/Float/Short values, sanity drops with reason)
  go to **Python stdout** → captured by `/api/utils/run` Next.js route
  → forwarded as SSE to the browser. The dashboard discards them
  silently because they aren't valid JSON event lines. **They are
  visible in the terminal where `npm run dev` runs the dashboard.**
- The progress callback (`{type: "progress", symbol, count, total}`)
  still drives the Step 3 progress bar in the UI.

### Files involved

| Path | Role |
|---|---|
| `get_float.py`                                       | Hybrid sourcing logic. New helpers `polygon_shares_outstanding()` / `polygon_short_interest()`. Sanity gates. Original yfinance-only `get_float()` preserved at file bottom under `LEGACY (pre-2026-05-03)`. |
| `trading_dashboard/src/app/api/low-float/route.ts`   | SQL guard in `extraWhere`: `shares_outstanding > 0 AND float_value <= shares_outstanding AND (shares_short IS NULL OR shares_short <= shares_outstanding * 1.5)`. Defense-in-depth in case stale broken rows are still in the DB before Step 3 reruns. |
| `utils_pipeline.py`                                  | No change — still spawns `get_float.get_float()` as Step 3. |

### Sanity gate threshold (kept in sync across two layers)

```python
# get_float.py
SANITY_MAX_SHORT_TO_SO_RATIO = 1.5
```

```typescript
// /api/low-float/route.ts (extraWhere)
shares_short <= shares_outstanding * 1.5
```

The 1.5 threshold allows real naked-short outliers (RDGT-like cases
where `Short ≈ SO`, ratio ~1.0 confirmed via stockanalysis.com) but
blocks the yfinance bug pattern (ratios from 100× to 100,000×).

### What this fixed

Before the migration, the `Stocks` registry had:

| Inconsistency in `Stocks` (2,943 rows) | Rows | % |
|---|---:|---:|
| `Float > Shares Outstanding` (mathematically impossible) | 921 | 31.3 % |
| `Shares Short > Shares Outstanding` (improbable / bug)   | 784 | 26.7 % |
| `Shares Short > 5× Shares Outstanding` (definite bug)    | 774 | 26.3 % |

Pattern: yfinance returned `sharesOutstanding` at the wrong magnitude
(typically 1,000–100,000× too small) for two recurring cases:
**ADRs of foreign companies** (TEF, VOD, TLK, NMR, …) — yfinance
mis-handles the ADR↔underlying conversion; **recent reverse stock
splits** — yfinance keeps a stale field after the split.

After the migration, those sources are clean (Polygon SO comes from
SEC filings via CIK; Short Interest comes from FINRA file directly).
Inside the `/low-float` scanner, only ~7 rows remained visibly broken
to the operator before the Step 3 rerun + the SQL guard catches them
all.

### What Polygon doesn't cover, and the failure mode

The Polygon Ticker Overview returns `NOT_FOUND` for some recently-
delisted, recently-restructured, or thinly-covered tickers (e.g.
SONN at the time of writing). For those:

- `shares_outstanding` ends up `NULL` in MySQL
- The `/low-float` scanner's `shares_outstanding > 0` guard excludes
  the row from the candidate list
- Trade-off: we lose some legitimate small-caps from the scanner
  rather than display them with corrupted data

The operator-facing impact is acceptable for the strategy (low-float
momentum prioritises confidence in the signal over coverage breadth),
but worth knowing when a previously-visible ticker disappears.

### Polygon endpoints used

```
GET https://api.polygon.io/v3/reference/tickers/{ticker}
    ?apiKey=…
    → results.weighted_shares_outstanding   (or NULL)

GET https://api.polygon.io/stocks/v1/short-interest
    ?ticker={ticker}
    &sort=settlement_date.desc
    &limit=1
    &apiKey=…
    → results[0].short_interest             (most recent FINRA report)
    + results[0].days_to_cover              (bonus, not yet stored)
    + results[0].avg_daily_volume           (bonus, not yet stored)
    + results[0].settlement_date            (the FINRA cycle date)
```

API key is read from `POLYGON_API_KEY` environment variable, with the
hardcoded fallback that already lives in the rest of the Python
modules (`0oQUg6UgH34Ala4OF_YYObsT_5Jh2IBJ`).

Subscription tier verified at migration time: both endpoints respond
200 OK with the operator's current account. If a future tier change
breaks them, watch for 401/403 → the helpers return None and the
sanity gates do their job.

### Pending: Schwab for Float

Float still flows through yfinance (the corrupted source) because
Polygon does not expose it. The only investigated source that does is
the **Charles Schwab Trader API** (`marketCapFloat` field on the
`instruments?projection=fundamental` endpoint), which is FREE with a
Schwab brokerage account but requires a 1–2 week dev-app approval.
The operator does not yet have approval — when it lands, replace the
yfinance call inside `get_float()` with a Schwab call and remove the
last yfinance dependency from this code path.

For the comparison of all 4 sources investigated (yfinance, Polygon,
IB Reuters Fundamentals, Schwab) and the rationale for the hybrid
choice, see the section before this one in the project history (the
investigation lived here as "Planned improvement" before this entry
replaced it on 2026-05-03).

### Future bonus: `days_to_cover`

The Polygon Short Interest response already includes `days_to_cover`
(short_interest / avg_daily_volume) — a classic short-squeeze signal.
Currently we only persist `short_interest`. Adding a `days_to_cover`
column to `Stocks` and to the `/low-float` dashboard would surface
this metric without any new API call. Worth considering as a small
follow-up.

## Conventions

- Timezone: All timestamps convert from UTC to Costa Rica time (`America/Costa_Rica`, UTC-6)
- API keys are hardcoded in individual modules (Polygon key referenced directly in RESTClient calls)
- MySQL credentials: root user on localhost:3306, database `histFinanData`
- The codebase mixes Spanish and English in comments and variable names
- Python 3.9 (multiple venvs exist: `myenv`, `nuevo`, `entorno`, `Crear`, `un`, `#`)
- The active virtual environment is `myenv`
- IB Client IDs: 0 for dashboard, 25-28 for trade signal consumers, 200-1000 random for manual orders, 99 for simulator
