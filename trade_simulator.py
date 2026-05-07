"""
Trade Simulator
===============
Simulates the consumer_process from multiprocessing_websocket_rv_hour.py
Implements the full trading logic from lines 2326-2609
"""

import mysql.connector
import logging
from datetime import datetime
import time
import csv
import pytz

# Import configuration from trading_config
from trading_config import (
    RELATIVE_VOLUME_FACTOR,
    MAX_LOSS_TOLERANCE_PER_TRADE,
    INCREASE_FROM_OPEN,
    TRADE_SIGNAL_LIMIT,
    ACTIVITY_PERCENTAGE,
    SIMULATOR_CONSUMER_ID,
    SIMULATOR_PORT,
    STALE_THRESHOLD_MINUTES
)

# Setup logging to write to trading_system.log
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Only add handler if not already added (prevent duplicates)
if not logger.handlers:
    file_handler = logging.FileHandler("trading_system.log")
    file_handler.setLevel(logging.INFO)
    formatter = logging.Formatter(
        '[%(asctime)s] [TRADE_SIMULATOR] [%(levelname)s] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)


# ============================================================================
# Helper functions (copied from multiprocessing_websocket_rv_hour.py)
# ============================================================================

def get_relative_volume_hour(hour, am_pm, mysql_cursor):
    """Load relative volume data for a specific hour"""
    mysql_cursor.execute('''
        SELECT `symbol`, `relative_volume`
            FROM RelativeVolumeRatioHour
                WHERE hour = %s
                AND amPm = %s
    ''', (hour, am_pm))

    rows = mysql_cursor.fetchall()
    relative_volume_list_hashmap = {row[0]: row[1] for row in rows}
    return relative_volume_list_hashmap


def condition_affects_ohlcv_v_p(trade_conditions, conditions, index):
    """Check if trade conditions affect OHLCV components (OR logic)"""
    # None = plain vanilla trade => always updates OHLCV
    # index -> 0 updates_open_close
    # index -> 1 updates_high_low(price)
    # index -> 2 updates_volume

    if trade_conditions is None:
        return 1

    if not trade_conditions:
        return 0

    affects = 0

    for cond_id in trade_conditions:
        cond = conditions.get(cond_id)
        if cond and cond[index]:
            affects = 1  # If any condition is true, it affects
            break  # Exit loop since we found at least one true

    return affects


def condition_affects_ohlcv_component(trade_conditions, conditions, index):
    """Check if trade conditions affect OHLCV components (AND logic)"""
    # None = plain vanilla trade => always updates OHLCV
    # index -> 0 updates_open_close
    # index -> 1 updates_high_low(price)
    # index -> 2 updates_volume

    if trade_conditions is None:
        return 1

    if not trade_conditions:
        return 0

    affects = 0

    for cond_id in trade_conditions:
        cond = conditions.get(cond_id)
        if cond and cond[index]:
            affects = 1
        else:
            return 0

    return affects


def load_conditions_bool_map(path: str):
    """Load trade conditions from CSV file"""
    # Treat empty values as True (allow updates) instead of False
    # This handles conditions like 63 (Financial Status - Deficient) which have empty CSV values
    def to_bool(s):
        s_clean = s.strip().lower()
        if not s_clean:  # Empty string → True (allow updates)
            return True
        return s_clean in ("true", "1", "yes", "y")

    m = {}
    with open(path, newline="", encoding="utf-8") as f:
        r = csv.DictReader(f)
        for row in r:
            cid = int(row["id"])
            m[cid] = (
                to_bool(row["updates_open_close"]),
                to_bool(row["updates_high_low"]),
                to_bool(row["updates_volume"]),
            )
    return m


def get_current_hour():
    """Get current hour in Costa Rica timezone (12-hour format)"""
    costa_rica_tz = pytz.timezone('America/Costa_Rica')
    utc_now = datetime.now(pytz.utc)
    cr_time = utc_now.astimezone(costa_rica_tz)
    return int(cr_time.strftime("%I"))


def get_current_minute():
    """Get current minute"""
    return int(datetime.now().strftime("%M"))


def get_am_pm():
    """Get AM/PM in Costa Rica timezone"""
    costa_rica_tz = pytz.timezone('America/Costa_Rica')
    utc_now = datetime.now(pytz.utc)
    cr_time = utc_now.astimezone(costa_rica_tz)
    return "AM" if cr_time.hour < 12 else "PM"


def get_symbol_list():
    """Get list of symbols from database"""
    db_connection = mysql.connector.connect(
        host="localhost",
        port=3306,
        user="root",
        password="E_I$S5PFri",
        database="histFinanData"
    )
    cursor = db_connection.cursor()

    # Get symbols from Stocks table
    cursor.execute("SELECT ticker FROM Stocks")
    symbols = [row[0] for row in cursor.fetchall()]

    cursor.close()
    db_connection.close()

    return symbols


def get_stock_float_map():
    """Get stock float values"""
    db_connection = mysql.connector.connect(
        host="localhost",
        port=3306,
        user="root",
        password="E_I$S5PFri",
        database="histFinanData"
    )
    cursor = db_connection.cursor(dictionary=True)

    cursor.execute("SELECT ticker, float_value FROM Stocks")
    float_map = {row['ticker']: row['float_value'] for row in cursor.fetchall()}

    cursor.close()
    db_connection.close()

    return float_map


def simulate_consumer_process(relative_volume_factor, results_queue=None, trade_signal_queue=None):
    """
    Simulates the consumer_process behavior with full trading logic
    from lines 2326-2609 of multiprocessing_websocket_rv_hour.py

    Args:
        relative_volume_factor: The CALCULATED RV factor from the dashboard (e.g., 1.269)
                               This is the value displayed in Trading Activity Metrics
        results_queue: multiprocessing.Queue to put results into (for multiprocessing mode)
        trade_signal_queue: multiprocessing.Queue to put trade signals when Rule 1/2 met

    Returns:
        dict: Summary of the simulation (if results_queue is None)
              None (if results_queue is provided - results go to queue instead)
    """

    logger.info("=" * 70)
    logger.info("TRADE SIMULATION STARTED - Full Consumer Process Logic")
    logger.info("=" * 70)

    # ========================================================================
    # CONFIGURATION (imported from trading_config.py)
    # ========================================================================

    # Use imported constants from trading_config
    increase_open = INCREASE_FROM_OPEN
    trade_signal_limit = TRADE_SIGNAL_LIMIT
    percentage = ACTIVITY_PERCENTAGE
    consumer_id = SIMULATOR_CONSUMER_ID
    port = SIMULATOR_PORT
    stale_threshold_minutes_config = STALE_THRESHOLD_MINUTES

    # Log configuration
    logger.info("Configuration:")
    logger.info(f"  RELATIVE_VOLUME_FACTOR: {RELATIVE_VOLUME_FACTOR}")
    logger.info(f"  MAX_LOSS_TOLERANCE_PER_TRADE: {MAX_LOSS_TOLERANCE_PER_TRADE}")
    logger.info(f"  INCREASE_FROM_OPEN: {INCREASE_FROM_OPEN}%")
    logger.info(f"  TRADE_SIGNAL_LIMIT: {TRADE_SIGNAL_LIMIT}")
    logger.info(f"  ACTIVITY_PERCENTAGE: {ACTIVITY_PERCENTAGE}")
    logger.info(f"  SIMULATOR_CONSUMER_ID: {SIMULATOR_CONSUMER_ID}")
    logger.info(f"  SIMULATOR_PORT: {SIMULATOR_PORT}")

    # ========================================================================
    # DATABASE CONNECTION
    # ========================================================================

    db_connection = mysql.connector.connect(
        host="localhost",
        port=3306,
        user="root",
        password="E_I$S5PFri",
        database="histFinanData"
    )
    mysql_cursor = db_connection.cursor(dictionary=True)

    # Clear old simulation data
    logger.info("Clearing previous simulation data...")
    mysql_cursor.execute("DELETE FROM TradeSignalsBuyPerSecond WHERE temp_action = 'simulation'")
    db_connection.commit()
    logger.info("Previous simulation data cleared")

    # ========================================================================
    # DETERMINE WHICH SYMBOL TO SIMULATE (from RawTrades)
    # ========================================================================
    # Get the unique symbol from RawTrades
    mysql_cursor.execute("SELECT DISTINCT symbol FROM RawTrades LIMIT 1")
    symbol_row = mysql_cursor.fetchone()

    if not symbol_row:
        logger.error("No symbol found in RawTrades")
        mysql_cursor.close()
        db_connection.close()
        result = {
            'status': 'error',
            'message': 'No trades in database'
        }
        if results_queue is not None:
            results_queue.put(result)
            return None
        else:
            return result

    simulated_symbol = symbol_row['symbol']
    logger.info(f"Simulating trades for: {simulated_symbol}")

    # Use ONLY this symbol (not all symbols from database)
    symbols = [simulated_symbol]

    # Get stock float values
    stock_float_hashmap = get_stock_float_map()

    # High short interest stocks (empty for simulation)
    high_short_interest_stocks = set()

    # Current minute
    current_minute = get_current_minute()
    open_map_timestamp = 0

    # OHLCV tracking dictionaries (ONLY for the simulated symbol)
    trade_consumer_close_map = {simulated_symbol: 0}
    trade_consumer_high_map = {simulated_symbol: 0}
    trade_consumer_low_map = {simulated_symbol: 0}
    trade_consumer_open_map = {simulated_symbol: 0}
    trade_consumer_open_map_timestamp = {simulated_symbol: 0}
    trade_consumer_volume_map = {simulated_symbol: 0}
    trade_per_minute_map = {simulated_symbol: 0}

    # Activity tracking
    trades_by_second_map_set = {simulated_symbol: set()}
    activity_second_count_hashmap = {simulated_symbol: 0}

    # Trade signal tracking
    trade_signals_memory_hashmap = {}
    trade_signals_track_low_activity = {}
    trade_signals_track_stock_price = {}
    trade_signals_to_buy = {}

    # Trades storage
    trades_by_symbol = {}

    # Real-time positions (empty for simulation)
    real_time_positions = {}

    # Load conditions for OHLCV filtering
    conditions = load_conditions_bool_map("polygon_conditions_trade_stocks.csv")

    # Get the hour from the first trade
    mysql_cursor.execute("SELECT transactions FROM RawTrades ORDER BY id ASC LIMIT 1")
    first_trade = mysql_cursor.fetchone()
    unix_timestamp_ns = first_trade['transactions']

    # Convert nanoseconds to datetime for hour extraction
    from datetime import datetime
    unix_timestamp_seconds = unix_timestamp_ns / 1_000_000_000  # nanoseconds → seconds
    dt = datetime.fromtimestamp(unix_timestamp_seconds)
    simulated_hour = dt.hour
    simulated_year = dt.year
    simulated_month = dt.month
    simulated_day = dt.day

    # Use the RV value passed from the Trading Activity Metrics panel
    # NOTE: Despite the parameter name, this is the AVERAGE HOURLY VOLUME in shares, not a factor
    logger.info(f"Using Relative Volume (avg hourly volume) from screen: {relative_volume_factor:,.0f} shares for {simulated_symbol} at hour {simulated_hour}:00")

    # ========================================================================
    # SIMULATION RESULTS TRACKING
    # ========================================================================

    trade_signals_generated = []
    stop_loss_triggers = []
    take_profit_triggers = []
    short_squeeze_signals = []
    price_tracking_signals = []
    low_activity_signals = []

    # ========================================================================
    # QUERY TRADES FROM DATABASE (simulating queue)
    # ========================================================================

    mysql_cursor.execute("""
        SELECT
            symbol,
            close as price,
            volume,
            transactions as timestamp,
            conditions,
            trade_id as id,
            exchange,
            trf_id
        FROM RawTrades
        ORDER BY id ASC
    """)

    trades = mysql_cursor.fetchall()

    # DEBUG: Show first trade raw data
    if trades:
        logger.info(f"[SQL DEBUG] First trade from DB: {trades[0]}")

    if not trades:
        logger.info("No trades found in RawTrades table")
        mysql_cursor.close()
        db_connection.close()
        result = {
            'status': 'completed',
            'trade_count': 0,
            'signals_generated': 0,
            'message': 'No trades to process'
        }
        if results_queue is not None:
            results_queue.put(result)
            return None
        else:
            return result

    # DEBUG: Show unique symbols in RawTrades
    unique_symbols = set(trade['symbol'] for trade in trades)
    logger.info(f"Processing {len(trades)} trades from {len(unique_symbols)} unique symbols")
    logger.info(f"Symbols in RawTrades: {sorted(list(unique_symbols))[:10]}...")

    # ========================================================================
    # PROCESS EACH TRADE (Main Loop - lines 2326-2609)
    # ========================================================================

    trade_count = 0
    rv_check_count = 0  # Track how many times we check RV
    rv_passed_count = 0  # Track how many times RV threshold is met
    trades_with_price_increase = 0  # Count trades with price increase >= threshold
    first_rv_exceeded_trade = None  # Track first trade where RV was exceeded

    # Rule 1: Track first trade exceeding 2% increase with volume >= 100
    first_2pct_increase_trade = None

    # Rule 2: Track first trade with 2% increase AND cumulative volume >= RV threshold
    first_2pct_with_rv_trade = None

    # Debug counters
    debug_condition_pass_count = 0
    debug_volume_pass_count = 0
    debug_price_check_count = 0

    for trade in trades:
        # Extract trade data (same as line 2289-2296)
        symbol = trade["symbol"]

        # Capture trade arrival time (for latency measurement)
        trade_arrival_time = time.time()

        trade_price = float(trade["price"])
        trade_volume = int(trade["volume"]) if trade["volume"] is not None else 0

        # Convert Unix nanoseconds (from Polygon) to milliseconds
        unix_timestamp_ns = trade["timestamp"]

        # DEBUG: Log first 3 trades to verify timestamp conversion
        if trade_count < 3:
            logger.info(f"[TIMESTAMP DEBUG] Trade #{trade_count + 1}: raw={unix_timestamp_ns}, type={type(unix_timestamp_ns)}")

        unix_timestamp = int(unix_timestamp_ns / 1_000_000)  # nanoseconds → milliseconds

        if trade_count < 3:
            logger.info(f"[TIMESTAMP DEBUG] Converted to ms: {unix_timestamp}, seconds: {unix_timestamp // 1000 % 60}")

        # Parse conditions from database string format
        # Database stores: "None" (string) or "12, 37" (comma-separated string)
        # Code expects: None (NoneType) or [12, 37] (list of ints)
        conditions_raw = trade["conditions"]
        if conditions_raw is None or conditions_raw == "None" or conditions_raw == "":
            trade_conditions = None  # Vanilla trade, no special conditions
        else:
            # Optimized: skip strip() if no spaces, use try/except only for errors
            try:
                trade_conditions = [int(c) for c in conditions_raw.split(",")]
            except (ValueError, AttributeError):
                trade_conditions = None  # Fallback for invalid format

        trade_id = trade["id"]
        trade_exchange = trade["exchange"]
        trade_trf_id = trade["trf_id"]

        # Skip if symbol not in our list
        if symbol not in symbols:
            continue

        trade_count += 1

        # Debug logging for first 5 trades
        if trade_count <= 5:
            logger.info(f"[DEBUG] Trade #{trade_count}: Price=${trade_price:.2f}, Vol={trade_volume}, Conditions_raw='{conditions_raw}', Parsed={trade_conditions}")

        # # ====================================================================
        # # LINE 2326-2337: Store trade in trades_by_symbol
        # # ====================================================================

        # if symbol not in trades_by_symbol:
        #     trades_by_symbol[symbol] = []

        # trades_by_symbol[symbol].append({
        #     "price": trade_price,
        #     "volume": trade_volume,
        #     "timestamp": unix_timestamp,
        #     "id": trade_id,
        #     "conditions": trade_conditions,
        #     "exchange": trade_exchange,
        #     "trf_id": trade_trf_id
        # })

        # ====================================================================
        # LINE 2339-2359: Initialize OPEN price on first trade with volume >= 100
        # ====================================================================

        if trade_consumer_open_map[symbol] == 0:
            condition_check_open = condition_affects_ohlcv_component(trade_conditions, conditions, 0)

            # Debug first 10 trades
            if trade_count <= 10:
                logger.info(f"[OPEN CHECK] Trade #{trade_count}: Price=${trade_price:.2f} Vol={trade_volume} Cond_check={condition_check_open} Conditions={trade_conditions}")

            if condition_check_open:
                # OPEN = first trade with volume >= 100
                if trade_volume is not None and trade_volume >= 100:
                    timestamp_in_seconds = unix_timestamp // 1000
                    trades_by_second_map_set[symbol].add(timestamp_in_seconds % 60)
                    activity_second_count_hashmap[symbol] = len(trades_by_second_map_set[symbol])

                    trade_consumer_open_map_timestamp[symbol] = unix_timestamp
                    trade_consumer_open_map[symbol] = trade_price
                    trade_consumer_close_map[symbol] = trade_price
                    trade_consumer_high_map[symbol] = trade_price
                    trade_consumer_low_map[symbol] = trade_price

                    logger.info(f"[OPEN SET] OPEN price set to ${trade_price:.2f} at trade #{trade_count} with volume {trade_volume}")

        # ====================================================================
        # LINE 2361-2368: Update HIGH/LOW/CLOSE
        # ====================================================================

        condition_check = condition_affects_ohlcv_v_p(trade_conditions, conditions, 1)
        if trade_count <= 5:
            logger.info(f"[DEBUG] Trade #{trade_count}: Condition check (high/low) = {condition_check}")

        if condition_check:
            debug_condition_pass_count += 1
            if trade_volume is not None and trade_volume >= 100:
                debug_volume_pass_count += 1
                trade_consumer_close_map[symbol] = trade_price
                trade_consumer_high_map[symbol] = max(trade_consumer_high_map[symbol], trade_price)
                trade_consumer_low_map[symbol] = min(trade_consumer_low_map[symbol], trade_price)

                # Track trades with price increase >= threshold
                if trade_consumer_open_map[symbol] > 0:
                    debug_price_check_count += 1
                    open_price = trade_consumer_open_map[symbol]
                    price_increase_pct = ((trade_price - open_price) / open_price) * 100
                    if trade_count <= 5:
                        logger.info(f"[DEBUG] Trade #{trade_count}: OPEN=${open_price:.2f}, Price=${trade_price:.2f}, Increase={price_increase_pct:.2f}%")
                    if price_increase_pct >= increase_open:
                        trades_with_price_increase += 1
                        if trade_count <= 5:
                            logger.info(f"[DEBUG] Trade #{trade_count}: ✓ PASSES 2% threshold!")

        # ====================================================================
        # LINE 2370-2388: Update VOLUME and track activity
        # ====================================================================

        if condition_affects_ohlcv_v_p(trade_conditions, conditions, 2):
            if trade_volume is not None:
                if trade_volume >= 100:
                    trade_consumer_volume_map[symbol] += trade_volume

                    timestamp_in_seconds = unix_timestamp // 1000
                    trades_by_second_map_set[symbol].add(timestamp_in_seconds % 60)
                    activity_second_count_hashmap[symbol] = len(trades_by_second_map_set[symbol])

        # ====================================================================
        # RULE 1: Track if price increase threshold (2%) has been met
        # ====================================================================

        price_threshold_met = False
        if first_2pct_increase_trade is None:
            if condition_affects_ohlcv_v_p(trade_conditions, conditions, 1):
                if trade_volume is not None and trade_volume >= 100:
                    if trade_consumer_open_map[symbol] > 0:
                        open_price = trade_consumer_open_map[symbol]
                        threshold_price = open_price * (1 + increase_open / 100)

                        if trade_price >= threshold_price:
                            price_threshold_met = True
                            increase_pct = ((trade_price - open_price) / open_price) * 100
                            cumulative_volume = trade_consumer_volume_map[symbol]
                            rv_threshold_volume = relative_volume_factor

                            first_2pct_increase_trade = {
                                'trade_number': trade_count,
                                'symbol': symbol,
                                'price': trade_price,
                                'volume': trade_volume,
                                'cumulative_volume': cumulative_volume,
                                'open': open_price,
                                'threshold': threshold_price,
                                'increase_pct': increase_pct,
                                'timestamp': unix_timestamp,
                                'exchange': trade_exchange
                            }

                            logger.info(f"📊 RULE1: {symbol} #{trade_count} ${trade_price:.2f} (OPEN ${open_price:.2f}) +{increase_pct:.1f}%")
        else:
            price_threshold_met = True  # Already met in a previous trade

        # ====================================================================
        # RULE 2: Check if cumulative volume >= RV threshold
        # When BOTH Rule 1 and Rule 2 are met → Send signal
        # ====================================================================

        if first_2pct_with_rv_trade is None and price_threshold_met:
            cumulative_volume = trade_consumer_volume_map[symbol]
            rv_threshold_volume = relative_volume_factor
            open_price = trade_consumer_open_map[symbol]

            # Check if cumulative volume meets threshold
            if cumulative_volume >= rv_threshold_volume:
                increase_pct = ((trade_price - open_price) / open_price) * 100
                threshold_price = open_price * (1 + increase_open / 100)

                first_2pct_with_rv_trade = {
                    'trade_number': trade_count,
                    'symbol': symbol,
                    'price': trade_price,
                    'volume': trade_volume,
                    'cumulative_volume': cumulative_volume,
                    'rv_threshold': rv_threshold_volume,
                    'open': open_price,
                    'threshold': threshold_price,
                    'increase_pct': increase_pct,
                    'timestamp': unix_timestamp,
                    'exchange': trade_exchange
                }

                logger.info(f"🎯 SIGNAL: {symbol} #{trade_count} ${trade_price:.2f} +{increase_pct:.1f}% vol={cumulative_volume:,}/{rv_threshold_volume:,.0f}")

                # Send ONE signal when BOTH rules are met
                if trade_signal_queue is not None:
                    signal_second = (unix_timestamp // 1000) % 60

                    logger.info(f"[SIGNAL DEBUG] unix_timestamp={unix_timestamp}, signal_second={signal_second}, active_seconds={activity_second_count_hashmap[symbol]}")

                    trade_signal_queue.put({
                        "action": "BUY",
                        "rule": "Both Rules Met",
                        "trade_number": trade_count,
                        "port": port,
                        "symbol": symbol,
                        "second": signal_second,
                        "active_seconds_count": activity_second_count_hashmap[symbol],
                        "trade_signals_count": trade_per_minute_map[symbol],
                        "timestamp": unix_timestamp,
                        "minute": current_minute,
                        "price": trade_price,
                        "volume": trade_volume,
                        "relative_volume_factor": relative_volume_factor,
                        "cumulative_volume": cumulative_volume,
                        "rv_threshold": rv_threshold_volume,
                        "news_time_window_minutes": 0,
                        "trade_signal_limit": trade_signal_limit,
                        "open_map": trade_consumer_open_map,
                        "open_map_timestamp": trade_consumer_open_map_timestamp[symbol],
                        "increase_open": increase_open,
                        "stale_threshold_minutes_config": stale_threshold_minutes_config,
                        "high": trade_consumer_high_map[symbol],
                        "low": trade_consumer_low_map[symbol],
                        "trade_arrival_time": trade_arrival_time,  # START time for latency measurement
                    })

                # STOP PROCESSING - Signal has been generated
                break

        # ====================================================================
        # LINE 2397-2424: Real-time position monitoring (stop-loss/take-profit)
        # ====================================================================

        # if symbol in real_time_positions:
        #     bot_price = real_time_positions[symbol]

        #     # Stop-loss check
        #     if trade_consumer_close_map[symbol] < bot_price * MAX_LOSS_TOLERANCE_PER_TRADE and trade_consumer_close_map[symbol] > 0:
        #         del real_time_positions[symbol]

        #         drop_percentage = ((bot_price - trade_consumer_close_map[symbol]) / bot_price) * 100
        #         logger.info(f"🔻 STOP-LOSS: {symbol} dropped {drop_percentage:.2f}%")

        #         stop_loss_triggers.append({
        #             "symbol": symbol,
        #             "close": trade_consumer_close_map[symbol],
        #             "entry": bot_price,
        #             "loss_pct": drop_percentage
        #         })

        #     # Take-profit check
        #     if trade_consumer_close_map[symbol] >= bot_price * 1.05:
        #         del real_time_positions[symbol]

        #         logger.info(f"✅ TAKE-PROFIT: {symbol} gained 5%+")

        #         take_profit_triggers.append({
        #             "symbol": symbol,
        #             "close": trade_consumer_close_map[symbol],
        #             "bot_price": bot_price
        #         })

        # ====================================================================
        # LINE 2426-2433: Use the relative volume factor from the dashboard
        # ====================================================================

        # DO NOT RECALCULATE - use the value passed from the Trading Activity Metrics
        # cumulative_volume = trade_consumer_volume_map[symbol]
        # relative_volume_factor_hour = relative_volume_factor

        # ====================================================================
        # LINE 2435-2453: Short squeeze detection
        # ====================================================================

        # if symbol in high_short_interest_stocks:
        #     if trade_consumer_open_map[symbol] > 0:
        #         open_price = trade_consumer_open_map[symbol]
        #         price_change_percentage = ((trade_consumer_close_map[symbol] - open_price) / open_price) * 100

        #         if price_change_percentage > (increase_open + 2) and symbol not in trade_signals_memory_hashmap:
        #             logger.info(f"🔥 SHORT SQUEEZE: {symbol} - Change: {price_change_percentage:.2f}%")
        #             trade_signals_memory_hashmap[symbol] = 1

        #             active_seconds_count = len(trades_by_second_map_set[symbol])

        #             short_squeeze_signals.append({
        #                 "symbol": symbol,
        #                 "price_change": price_change_percentage,
        #                 "open": open_price,
        #                 "close": trade_consumer_close_map[symbol]
        #             })

        # ====================================================================
        # LINE 2455-2489: Price tracking signals
        # ====================================================================

        # if symbol in trade_signals_track_stock_price:
        #     percentage_change = ((trade_consumer_close_map[symbol] - trade_signals_track_stock_price[symbol]) / trade_signals_track_stock_price[symbol]) * 100

        #     if percentage_change >= increase_open:
        #         del trade_signals_track_stock_price[symbol]

        #         logger.info(f"📈 PRICE TRACKING: {symbol} - Change: {percentage_change:.2f}%")

        #         active_seconds_count = len(trades_by_second_map_set[symbol])

        #         price_tracking_signals.append({
        #             "symbol": symbol,
        #             "percentage_change": percentage_change,
        #             "price": trade_consumer_close_map[symbol]
        #         })

        # ====================================================================
        # LINE 2493-2529: Low activity tracking
        # ====================================================================

        # if symbol in trade_signals_track_low_activity:
        #     current_time = datetime.now()
        #     current_second = current_time.second

        #     elapsed_seconds = current_second - open_map_timestamp
        #     elapsed_seconds_33_percent = elapsed_seconds * percentage

        #     active_seconds_count = len(trades_by_second_map_set[symbol])

        #     if active_seconds_count > elapsed_seconds_33_percent:
        #         del trade_signals_track_low_activity[symbol]

        #         logger.info(f"🔄 LOW ACTIVITY RECOVERED: {symbol}")

        #         low_activity_signals.append({
        #             "symbol": symbol,
        #             "active_seconds": active_seconds_count
        #         })

        # ====================================================================
        # LINE 2531-2607: Main relative volume trigger
        # ====================================================================

        # Log RV factor for debugging (first 20 trades)
        # rv_check_count += 1
        # if rv_check_count <= 20:
        #     logger.info(f"[DEBUG] {symbol}: cumulative_vol={cumulative_volume}, rv_factor_from_dashboard={relative_volume_factor_hour:.3f}, threshold={RELATIVE_VOLUME_FACTOR}")

        # if relative_volume_factor_hour >= RELATIVE_VOLUME_FACTOR:
        #     rv_passed_count += 1

        #     # Track first trade where RV was exceeded
        #     if first_rv_exceeded_trade is None:
        #         first_rv_exceeded_trade = trade_count

        #     if symbol not in trade_signals_memory_hashmap:
        #         trade_signals_memory_hashmap[symbol] = cumulative_volume

        #         if trade_consumer_open_map[symbol] == 0:
        #             continue

        #         active_seconds_count = len(trades_by_second_map_set[symbol])

        #         # Generate trade signal
        #         trade_signal = {
        #             "symbol": symbol,
        #             "active_seconds": active_seconds_count,
        #             "open": trade_consumer_open_map[symbol],
        #             "close": trade_consumer_close_map[symbol],
        #             "high": trade_consumer_high_map[symbol],
        #             "low": trade_consumer_low_map[symbol],
        #             "volume": cumulative_volume,
        #             "relative_volume_factor": relative_volume_factor_hour,
        #             "timestamp": unix_timestamp
        #         }

        #         # Check price increase
        #         open_price = trade_consumer_open_map[symbol]
        #         price_increase_pct = ((trade_consumer_close_map[symbol] - open_price) / open_price) * 100 if open_price > 0 else 0

        #         # Check activity
        #         current_time = datetime.now()
        #         current_second = current_time.second
        #         elapsed_seconds = current_second - open_map_timestamp
        #         elapsed_seconds_40_percent = elapsed_seconds * percentage

        #         # Determine purchase prediction
        #         if price_increase_pct < increase_open:
        #             # Track for potential future increase
        #             trade_signals_track_stock_price[symbol] = trade_consumer_open_map[symbol]
        #             purchasePrediction = f"Price increase less than {increase_open}%"
        #         elif trade_consumer_close_map[symbol] == trade_consumer_open_map[symbol]:
        #             purchasePrediction = "Doji Candle"
        #         elif active_seconds_count < elapsed_seconds_40_percent:
        #             trade_signals_track_low_activity[symbol] = active_seconds_count
        #             purchasePrediction = "Low activity"
        #         else:
        #             purchasePrediction = "BUY"
        #             trade_signals_to_buy[symbol] = trade_signals_to_buy.get(symbol, 0) + 1

        #             logger.info(f"💰 BUY SIGNAL: {symbol} @ ${trade_consumer_close_map[symbol]:.2f} RV:{relative_volume_factor_hour}x")

        #         trade_signal["prediction"] = purchasePrediction
        #         trade_signals_generated.append(trade_signal)

        #         # Persist signal to database (so analyzer can find it)
        #         low_float_value = "high"
        #         if symbol in stock_float_hashmap and stock_float_hashmap[symbol] is not None and stock_float_hashmap[symbol] < 5000000:
        #             low_float_value = "low"

        #         local_utc_timestamp_ms = int(time.time() * 1000)

        #         try:
        #             mysql_cursor.execute('''
        #                 INSERT INTO TradeSignalsBuyPerSecond (
        #                     `symbol`, `consumer_id`, `trade_activity_seconds`, `tradeSignalsCount`, `open`, `open_timestamp`, `close`, `last_trade_price`,
        #                     `ask_price`, `ask_timestamp`, `accumulated_volume`, `low_float`, `vwap`, `volume`,
        #                     `relative_volume`, `timestamp`, `averageDayVolume`, `purchasePrediction`, `aggregatesPerSecond`, `news_metadata`,
        #                     `relative_volume_hour`, `timestamp_unix`, `local_utc_timestamp`, `trade_id`, `exchange`, `trf_id`, `temp_action`, `high`, `low`
        #                 ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        #             ''', (
        #                 symbol,
        #                 consumer_id,
        #                 active_seconds_count,
        #                 trade_per_minute_map[symbol],
        #                 trade_consumer_open_map[symbol],
        #                 trade_consumer_open_map_timestamp[symbol],
        #                 trade_consumer_close_map[symbol],
        #                 trade_consumer_close_map[symbol],
        #                 0,  # ask_price
        #                 "---",  # ask_timestamp
        #                 cumulative_volume,
        #                 low_float_value,
        #                 10,  # vwap (placeholder)
        #                 cumulative_volume,
        #                 relative_volume_factor_hour,
        #                 time.time(),
        #                 0,  # averageDayVolume
        #                 purchasePrediction,
        #                 0,  # aggregatesPerSecond
        #                 "---",  # news_metadata
        #                 relative_volume_factor_hour,
        #                 unix_timestamp,
        #                 local_utc_timestamp_ms - unix_timestamp,
        #                 trade_id,
        #                 trade_exchange,
        #                 trade_trf_id,
        #                 "simulation",
        #                 trade_consumer_high_map[symbol],
        #                 trade_consumer_low_map[symbol]
        #             ))
        #             db_connection.commit()
        #         except Exception as e:
        #             logger.error(f"Error persisting signal for {symbol}: {e}")
        #             # Continue even if persistence fails

    # ========================================================================
    # SIMULATION COMPLETE
    # ========================================================================

    mysql_cursor.close()
    db_connection.close()

    buy_signals = len([s for s in trade_signals_generated if s["prediction"] == "BUY"])

    logger.info("=" * 70)
    logger.info(f"SIMULATION COMPLETED")
    logger.info(f"Total trades processed: {trade_count}")
    logger.info("")
    logger.info("DEBUG STATISTICS:")
    logger.info(f"  Trades passing condition check: {debug_condition_pass_count}")
    logger.info(f"  Trades with volume >= 100: {debug_volume_pass_count}")
    logger.info(f"  Trades with OPEN set for price check: {debug_price_check_count}")
    logger.info(f"  OPEN price for {simulated_symbol}: {trade_consumer_open_map[simulated_symbol]}")
    logger.info("")
    logger.info("RULE 1 RESULTS:")
    if first_2pct_increase_trade:
        logger.info(f"  First 2% increase at trade: #{first_2pct_increase_trade['trade_number']}")
        logger.info(f"  Symbol: {first_2pct_increase_trade['symbol']}")
        logger.info(f"  Price: ${first_2pct_increase_trade['price']:.2f} (OPEN: ${first_2pct_increase_trade['open']:.2f})")
        logger.info(f"  Increase: {first_2pct_increase_trade['increase_pct']:.2f}%")
        logger.info(f"  Volume: {first_2pct_increase_trade['volume']:,}")
        logger.info(f"  Exchange: {first_2pct_increase_trade['exchange']}")
    else:
        logger.info(f"  No trades exceeded 2% increase threshold")
    logger.info("")
    logger.info("RULE 2 RESULTS:")
    if first_2pct_with_rv_trade:
        logger.info(f"  First 2% + RV threshold at trade: #{first_2pct_with_rv_trade['trade_number']}")
        logger.info(f"  Symbol: {first_2pct_with_rv_trade['symbol']}")
        logger.info(f"  Price: ${first_2pct_with_rv_trade['price']:.2f} (OPEN: ${first_2pct_with_rv_trade['open']:.2f})")
        logger.info(f"  Increase: {first_2pct_with_rv_trade['increase_pct']:.2f}%")
        logger.info(f"  Volume: {first_2pct_with_rv_trade['volume']:,}")
        logger.info(f"  Cumulative Volume: {first_2pct_with_rv_trade['cumulative_volume']:,}")
        logger.info(f"  RV Threshold: {first_2pct_with_rv_trade['rv_threshold']:,.0f} shares")
        logger.info(f"  Exchange: {first_2pct_with_rv_trade['exchange']}")
    else:
        logger.info(f"  No trades met both 2% increase AND RV threshold")
    logger.info("")
    logger.info(f"Trades with price increase >= {increase_open}%: {trades_with_price_increase}")
    logger.info(f"First trade where RV exceeded: {first_rv_exceeded_trade if first_rv_exceeded_trade else 'Never'}")
    logger.info(f"RV threshold checks: {rv_check_count}")
    logger.info(f"RV threshold passed: {rv_passed_count} ({rv_passed_count/rv_check_count*100:.1f}% if rv_check_count > 0 else 0)" if rv_check_count > 0 else "RV threshold passed: 0")
    logger.info(f"Trade signals generated: {len(trade_signals_generated)}")
    logger.info(f"  - BUY signals: {buy_signals}")
    logger.info(f"  - Short squeeze: {len(short_squeeze_signals)}")
    logger.info(f"  - Price tracking: {len(price_tracking_signals)}")
    logger.info(f"  - Low activity: {len(low_activity_signals)}")
    logger.info(f"Stop-loss triggers: {len(stop_loss_triggers)}")
    logger.info(f"Take-profit triggers: {len(take_profit_triggers)}")
    logger.info("=" * 70)

    result = {
        'status': 'completed',
        'trade_count': trade_count,
        'signals_generated': len(trade_signals_generated),
        'buy_signals': buy_signals,
        'short_squeeze': len(short_squeeze_signals),
        'stop_loss': len(stop_loss_triggers),
        'take_profit': len(take_profit_triggers),
        'trade_signals': trade_signals_generated,
        'message': f'Simulation complete: {trade_count} trades, {buy_signals} BUY signals',
        'trades_with_price_increase': trades_with_price_increase,
        'first_rv_exceeded_trade': first_rv_exceeded_trade,
        'first_2pct_increase_trade': first_2pct_increase_trade,  # Rule 1 result
        'first_2pct_with_rv_trade': first_2pct_with_rv_trade,  # Rule 2 result
        'config': {
            'RELATIVE_VOLUME_FACTOR': RELATIVE_VOLUME_FACTOR,
            'MAX_LOSS_TOLERANCE_PER_TRADE': MAX_LOSS_TOLERANCE_PER_TRADE,
            'INCREASE_FROM_OPEN': INCREASE_FROM_OPEN,
            'TRADE_SIGNAL_LIMIT': TRADE_SIGNAL_LIMIT,
            'ACTIVITY_PERCENTAGE': ACTIVITY_PERCENTAGE,
            'SIMULATOR_CONSUMER_ID': SIMULATOR_CONSUMER_ID,
            'SIMULATOR_PORT': SIMULATOR_PORT
        }
    }

    # Put result in queue if multiprocessing, otherwise return it
    if results_queue is not None:
        results_queue.put(result)
        return None
    else:
        return result


if __name__ == "__main__":
    # For testing the simulator directly
    logging.basicConfig(
        level=logging.INFO,
        format='[%(asctime)s] [SIMULATOR] [%(levelname)s] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    result = simulate_consumer_process()
    print(f"\nSimulation Result:")
    print(f"  Status: {result['status']}")
    print(f"  Trades: {result['trade_count']}")
    print(f"  Signals: {result['signals_generated']}")
    print(f"  BUY signals: {result['buy_signals']}")
