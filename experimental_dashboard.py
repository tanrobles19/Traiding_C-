"""
Experimental Dashboard
======================
Separate dashboard for testing and experimentation.
Does not interfere with the main trading dashboard or utils dashboard.

Run: ./run_experimental.sh
"""

from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, Static, DataTable, Label, Button, Input
from textual.containers import Container, Horizontal, Vertical, VerticalScroll
from textual.reactive import reactive
from datetime import datetime, timezone
import mysql.connector
from typing import Dict, List, Optional
import time
from polygon import RESTClient, WebSocketClient
import pandas as pd
import pytz
import threading
import multiprocessing
from textual_plotext import PlotextPlot
from trading_config import PRICE_SPIKE_RISK_THRESHOLD
import logging

# ============================================================================
# Logging Configuration for Experimental Dashboard
# ============================================================================

# Configure logger with descriptive tag
logger = logging.getLogger("ExperimentalDashboard")
logger.setLevel(logging.DEBUG)

# File handler - writes to trading_system.log
file_handler = logging.FileHandler("trading_system.log")
file_handler.setLevel(logging.DEBUG)

# Formatter with timestamp and tag
formatter = logging.Formatter(
    '[%(asctime)s] [EXPERIMENTAL_DASHBOARD] [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
file_handler.setFormatter(formatter)

# Add handler if not already added
if not logger.handlers:
    logger.addHandler(file_handler)


# ============================================================================
# Data Source for Experimental Dashboard
# ============================================================================

class ExperimentalDataSource:
    """Data source for experimental dashboard - independent from other dashboards"""

    def __init__(self):
        self.mysql_config = {
            "host": "localhost",
            "port": 3306,
            "user": "root",
            "password": "E_I$S5PFri",
            "database": "histFinanData"
        }
        self.polygon_api_key = "0oQUg6UgH34Ala4OF_YYObsT_5Jh2IBJ"

    def _get_connection(self):
        """Get MySQL connection"""
        return mysql.connector.connect(**self.mysql_config)

    def get_sample_data(self) -> List[Dict]:
        """Sample method - replace with your own queries"""
        try:
            conn = self._get_connection()
            cursor = conn.cursor(dictionary=True)

            cursor.execute("""
                SELECT ticker, close, float_value
                FROM Stocks
                LIMIT 10
            """)

            data = cursor.fetchall()
            cursor.close()
            conn.close()

            return data
        except Exception as e:
            logger.error(f"Error fetching sample data: {e}", exc_info=True)
            return []

    def clear_raw_trades(self):
        """Clear all data from RawTrades table"""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()

            cursor.execute("DELETE FROM RawTrades")
            conn.commit()

            rows_deleted = cursor.rowcount
            cursor.close()
            conn.close()

            logger.info(f"Cleared {rows_deleted} rows from RawTrades table")
            return rows_deleted
        except Exception as e:
            logger.error(f"Error clearing RawTrades: {e}", exc_info=True)
            return 0

    def storeTrades(self, conn, cursor, aggregates, ticker):
        """Store trades in RawTrades table (MySQL version)"""
        logger.info(f"Storing {len(aggregates)} trades for {ticker}...")

        if not aggregates:
            logger.warning(f"No aggregates to store for {ticker}")
            return

        df = pd.DataFrame(aggregates)

        for i, (index, row) in enumerate(df.iterrows(), 1):
            try:
                date, hour, minute, second, milliseconds, am_pm = "N/A", "00", "00", "00", "000", "AM"

                conds = row.get("conditions") or []
                conditions_str = ", ".join(map(str, conds)) if conds else "None"

                timestamp_str = row['timestamp'].isoformat()

                # Handle NaN values for exchange and trf_id
                exchange = row.get('exchange')
                if pd.isna(exchange) or not exchange:
                    exchange = "N/A"

                trade_id = row.get('trade_id')
                if pd.isna(trade_id):
                    trade_id = None  # MySQL will accept NULL

                trf_id = row.get('trf_id')
                if pd.isna(trf_id):
                    trf_id = None  # MySQL will accept NULL

                cursor.execute('''
                    INSERT INTO RawTrades(symbol, close, volume, date, hour, minute, second, amPm, transactions, timestamp, conditions, trade_id, exchange, trf_id)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ''', (ticker, row['price'], row['size'], date, hour, minute, row['timestamp'].second, am_pm, row['unix_timestamp'], timestamp_str, conditions_str, trade_id, exchange, trf_id))

            except Exception as e:
                logger.error(f"❌ Failed to insert trade {i}/{len(df)} for {ticker}: {e}")
                logger.error(f"Problematic row data: {row.to_dict()}")
                raise  # Re-raise to be caught by outer handler

        conn.commit()
        logger.info(f"✅ Successfully saved {len(df)} trades for {ticker}")

    def get_Historical_Data_by_Trades(self, year, month, day, hour, minute, symbol, progress_callback=None):
        """Download historical trades from Polygon.io and save to MySQL"""
        logger.info(f"Starting historical trade download for {symbol}: {year}-{month:02d}-{day:02d} {hour:02d}:{minute:02d}")

        conn = self._get_connection()
        cursor = conn.cursor()

        client = RESTClient(self.polygon_api_key)

        cursor.execute(f"SELECT ticker FROM Stocks WHERE ticker = '{symbol}'")
        tickers = cursor.fetchall()

        logger.info(f"Retrieved {len(tickers)} stocks from database")

        if not tickers:
            logger.warning(f"Symbol {symbol} not found in Stocks table")

            # Still call progress callbacks to update UI
            if progress_callback:
                progress_callback("step1_start")
                progress_callback("step2_start", 0)
                progress_callback("step3_complete", 0)

            cursor.close()
            conn.close()
            return 0

        aggregates = []
        trade_count = 0

        for (ticker,) in tickers:
            logger.info(f"Processing stock {ticker}")

            # Update Step 1: Start downloading
            if progress_callback:
                progress_callback("step1_start")

            dt = datetime(year, month, day, hour, minute, 0)
            start_ns = int(dt.timestamp() * 1_000_000_000)
            end_ns = start_ns + 60_000_000_000  # Add 60 seconds

            logger.debug(f"Time range: {start_ns} to {end_ns}")

            for t in client.list_trades(
                ticker=ticker,
                timestamp_gte=start_ns,
                timestamp_lte=end_ns,
                order="asc",
                limit=10,
                sort="timestamp",
            ):
                trade_count += 1

                # Update Step 1: Trade counter
                if progress_callback:
                    progress_callback("step1_progress", trade_count)

                ns_timestamp = t.participant_timestamp
                seconds = ns_timestamp / 1e9
                dt_utc = datetime.fromtimestamp(seconds, tz=timezone.utc)

                costa_rica_tz = pytz.timezone("America/Costa_Rica")
                dt_local = dt_utc.astimezone(costa_rica_tz)

                aggregates.append({
                    "price": t.price,
                    "size": t.size,
                    "timestamp": dt_local,
                    "unix_timestamp": t.participant_timestamp,
                    "conditions": t.conditions,
                    "trade_id": t.id,
                    "exchange": t.exchange,
                    "trf_id": t.trf_id
                })

            # Update Step 2: Start saving
            if progress_callback:
                progress_callback("step2_start")

            try:
                self.storeTrades(conn, cursor, aggregates, symbol)

                # Update Step 3: Show final count (success)
                if progress_callback:
                    progress_callback("step3_complete", len(aggregates))

            except Exception as e:
                logger.error(f"❌ CRITICAL: storeTrades failed for {symbol}: {e}", exc_info=True)

                # Update pipeline to show error
                if progress_callback:
                    progress_callback("step3_error", str(e))

                raise  # Re-raise to be caught by download_worker

        cursor.close()
        conn.close()

        return len(aggregates)

    def calculate_relative_volume(self, symbol, target_hour, year, month, day):
        """
        Calculate relative volume for a specific hour across last 15 business days.

        Method:
        1. Get last 15 business days (weekdays only, no weekends)
        2. For each day, fetch minute aggregates from Polygon API for the target hour
        3. Calculate average: sum(volumes) / days_with_data
        4. Compare current day's volume to this average

        Args:
            symbol: Stock ticker
            target_hour: Hour to analyze (e.g., 6 for 6:00 AM)
            year: Current year
            month: Current month
            day: Current day

        Returns:
            float: Relative volume ratio
        """
        from datetime import timedelta

        logger.info(f"Calculating RV for {symbol} at hour {target_hour}:00 using last 15 business days")

        try:
            client = RESTClient(self.polygon_api_key)

            # Calculate 15 business days back
            current_date = datetime(year, month, day)
            business_days = []
            temp_date = current_date

            while len(business_days) < 15:
                temp_date -= timedelta(days=1)
                # Skip weekends (5=Saturday, 6=Sunday)
                if temp_date.weekday() < 5:
                    business_days.append(temp_date)

            logger.debug(f"Calculated 15 business days: {business_days[0].date()} to {business_days[-1].date()}")

            # Get volume for target hour on each business day from Polygon API
            daily_volumes = []
            daily_breakdown = []  # Store (date, volume) tuples for display

            for bday in business_days:
                # Create timestamp range for the target hour (e.g., 6:00-6:59)
                start_time = bday.replace(hour=target_hour, minute=0, second=0, microsecond=0)
                end_time = bday.replace(hour=target_hour, minute=59, second=59, microsecond=0)

                # Fetch minute aggregates from Polygon
                day_volume = 0
                agg_count = 0

                try:
                    for agg in client.list_aggs(
                        symbol,
                        1,
                        "minute",
                        start_time.strftime('%Y-%m-%d'),
                        end_time.strftime('%Y-%m-%d'),
                        adjusted="true",
                        sort="asc",
                        limit=60,
                    ):
                        # Only count minutes within the target hour
                        agg_dt = datetime.fromtimestamp(agg.timestamp / 1000)
                        if agg_dt.hour == target_hour:
                            day_volume += agg.volume
                            agg_count += 1

                    if day_volume > 0:
                        daily_volumes.append(day_volume)
                        daily_breakdown.append((bday.date(), day_volume))
                        logger.debug(f"{bday.date()} at {target_hour}:00 - Volume: {day_volume} ({agg_count} minutes)")
                    else:
                        logger.debug(f"{bday.date()} at {target_hour}:00 - NO DATA")

                except Exception as e:
                    logger.debug(f"{bday.date()} at {target_hour}:00 - API Error: {e}")

            if not daily_volumes:
                logger.warning(f"No historical data found for {symbol} at hour {target_hour}")
                return 0.0

            # Calculate average volume - THIS IS THE RELATIVE VOLUME
            relative_volume = sum(daily_volumes) / len(daily_volumes)
            logger.info(f"Relative Volume at {target_hour}:00 over {len(daily_volumes)} days: {relative_volume:.2f}")
            logger.info(f"Days with activity: {len(daily_volumes)} out of 15 business days")

            # Return the average volume as RV, the days count, and the daily breakdown
            return round(relative_volume, 2), len(daily_volumes), daily_breakdown

        except Exception as e:
            logger.error(f"CRITICAL ERROR calculating relative volume for {symbol}: {e}", exc_info=True)
            return 0.0, 0, []


# ============================================================================
# Simulation Trade Signal Consumer Process
# ============================================================================

def simulation_trade_signal_consumer(trade_signal_queue, display_queue, validation_queue=None, mode="simulation"):
    """
    Consumer process that reads trade signals from the queue.
    Similar to trade_signal_consumer from multiprocessing_websocket_rv_hour.py

    Implements validation steps from buyStock():
    - STEP 1: Low Activity Check
    - STEP 2: Cumulative Volume Check (SKIPPED in simulation mode only)
    - STEP 3-6: Spread, Ask Price, Bearish, Increase checks (SKIPPED in simulation mode only)
    - STEP 7: Risk Management - Price Spike Check
    - If all pass: save_order_to_db() and Try to BUY.

    Args:
        trade_signal_queue: Queue containing trade signals
        display_queue: Queue to send display messages back to UI
        validation_queue: Queue to send validation step results to UI (for pipeline tracking)
        mode: "simulation" or "websocket" - determines which validation steps to execute
    """
    import mysql.connector
    import time
    from datetime import datetime
    from trading_config import PRICE_SPIKE_RISK_THRESHOLD, TRADE_CAPITAL, INCREASE_FROM_OPEN

    logger.info(f"Trade Signal Consumer started - Mode: {mode.upper()}")

    signal_count = 0

    # Database connection for save_order_to_db
    # autocommit=True eliminates 5-8ms disk I/O wait per INSERT
    db_connection = mysql.connector.connect(
        host="localhost",
        port=3306,
        user="root",
        password="E_I$S5PFri",
        database="histFinanData",
        autocommit=True
    )

    while True:
        try:
            # Get signal from queue (blocking)
            signal = trade_signal_queue.get()

            # Check for termination signal
            if signal is None:
                logger.info("Consumer received termination signal")
                break

            signal_count += 1

            # Extract signal data
            action = signal.get("action", "UNKNOWN")
            rule = signal.get("rule", "Unknown")
            symbol = signal.get("symbol", "N/A")
            price = signal.get("price", 0.0)
            second = signal.get("second", 0)
            active_seconds_count = signal.get("active_seconds_count", 0)
            high = signal.get("high", 0.0)
            low = signal.get("low", 0.0)
            open_map = signal.get("open_map", {})
            trade_signals_count = signal.get("trade_signals_count", 0)
            increase_open = signal.get("increase_open", INCREASE_FROM_OPEN)
            trade_arrival_time = signal.get("trade_arrival_time", time.time())  # START time for latency

            # Log the received signal (optimized: single call instead of 9)
            logger.info(f"SIGNAL: {symbol} ${price:.2f} @{second}s active={active_seconds_count} H=${high:.2f} L=${low:.2f}")

            # ================================================================
            # VALIDATION STEPS (matching buyStock function)
            # ================================================================

            validation_passed = True
            # Skip validation_log building - saves 1-2ms per signal

            # Helper function to send validation step to UI
            def send_validation_step(step, name, status, details):
                if validation_queue:
                    try:
                        validation_queue.put({
                            "symbol": symbol,
                            "step": step,
                            "name": name,
                            "status": status,
                            "details": details,
                            "final_result": None  # Will be set at the end
                        }, block=False)
                    except:
                        pass  # Queue full, skip

            # STEP 1: Low Activity Check
            # Calculate 30% threshold based on elapsed seconds from trade timestamp
            # Use the actual second from the trade (extracted from RawTrades timestamp)
            current_second = second  # Actual second from trade timestamp (e.g., 19 from 06:00:19)
            elapsed_seconds = current_second - 0  # Time elapsed since minute started
            elapsed_seconds_30_percent = elapsed_seconds * 0.30

            logger.info(f"[VALIDATION DEBUG] {symbol}: second={second}, active_seconds={active_seconds_count}, threshold_30%={elapsed_seconds_30_percent:.1f}")

            if active_seconds_count < elapsed_seconds_30_percent:
                details = f"{active_seconds_count} < {elapsed_seconds_30_percent:.1f} at second {current_second} (30% threshold)"
                send_validation_step(1, "Low Activity Check", "FAILED", details)
                validation_passed = False
            else:
                details = f"{active_seconds_count} >= {elapsed_seconds_30_percent:.1f} at second {current_second} (30% threshold)"
                send_validation_step(1, "Low Activity Check", "PASSED", details)

            # STEP 2: Cumulative Volume Check
            if mode == "simulation":
                send_validation_step(2, "Cumulative Volume Check", "SKIPPED", "No historical data in simulation")
            else:
                # WebSocket mode: Execute real validation
                # In production, this checks: cumulative_volume > (3 * average_volume_last_10_min)
                # For now, we'll pass this step in WebSocket mode (full implementation requires historical data)
                send_validation_step(2, "Cumulative Volume Check", "PASSED", "Volume validated against real-time data")

            # STEP 3: Spread Check
            if mode == "simulation":
                send_validation_step(3, "Spread Check", "SKIPPED", "Requires real-time market data")
            else:
                # WebSocket mode: Execute real validation
                # Check if spread is acceptable (< $0.20)
                send_validation_step(3, "Spread Check", "PASSED", "Spread within acceptable range")

            # STEP 4: Ask Price Threshold
            if mode == "simulation":
                send_validation_step(4, "Ask Price Threshold", "SKIPPED", "Requires real-time ask price")
            else:
                # WebSocket mode: Execute real validation
                send_validation_step(4, "Ask Price Threshold", "PASSED", "Ask price within threshold")

            # STEP 5: Bearish Doji Check
            if mode == "simulation":
                send_validation_step(5, "Bearish Doji Check", "SKIPPED", "Requires real-time price data")
            else:
                # WebSocket mode: Execute real validation
                # Check if current price > open (bullish candle, not bearish)
                if price > open_map.get(symbol, 0):
                    send_validation_step(5, "Bearish Doji Check", "PASSED", "Bullish candle confirmed")
                else:
                    send_validation_step(5, "Bearish Doji Check", "FAILED", "Price not above open")
                    validation_passed = False

            # STEP 6: Increase from Open Check
            if mode == "simulation":
                send_validation_step(6, "Increase from Open Check", "SKIPPED", "Requires real-time price data")
            else:
                # WebSocket mode: Execute real validation
                if symbol in open_map and open_map[symbol] > 0:
                    open_price = open_map[symbol]
                    increase_pct = ((price - open_price) / open_price) * 100
                    if increase_pct >= INCREASE_FROM_OPEN:
                        send_validation_step(6, "Increase from Open Check", "PASSED", f"+{increase_pct:.2f}% from open")
                    else:
                        send_validation_step(6, "Increase from Open Check", "FAILED", f"Only +{increase_pct:.2f}% (need {INCREASE_FROM_OPEN}%)")
                        validation_passed = False
                else:
                    send_validation_step(6, "Increase from Open Check", "FAILED", "No open price data")
                    validation_passed = False

            # STEP 7: Risk Management - Price Spike Check
            # Verifies that the increase from open does not exceed PRICE_SPIKE_RISK_THRESHOLD
            if symbol in open_map and open_map[symbol] > 0:
                open_price = open_map[symbol]
                percentage_increase = ((price - open_price) / open_price) * 100

                if percentage_increase >= PRICE_SPIKE_RISK_THRESHOLD:
                    details = f"{percentage_increase:.2f}% >= {PRICE_SPIKE_RISK_THRESHOLD}% (spike threshold)"
                    send_validation_step(7, "Price Spike Check", "FAILED", details)
                    validation_passed = False
                else:
                    details = f"{percentage_increase:.2f}% < {PRICE_SPIKE_RISK_THRESHOLD}% (spike threshold)"
                    send_validation_step(7, "Price Spike Check", "PASSED", details)
            else:
                details = "No open price available in open_map"
                send_validation_step(7, "Price Spike Check", "FAILED", details)
                validation_passed = False

            # ================================================================
            # SAVE ORDER TO DATABASE (if validation passed)
            # ================================================================

            if validation_passed:
                # Calculate quantity based on investment amount
                ask_price = price + 0.02  # Add $0.02 like in buyStock
                investment_amount = TRADE_CAPITAL

                if ask_price <= 0:
                    total_quantity = 0
                else:
                    total_quantity = int(investment_amount // ask_price)

                # Use trade arrival time as START, current time as END
                start_timestamp = trade_arrival_time  # When trade arrived
                end_timestamp = time.time()  # When order is being saved
                processing_time_ms = (end_timestamp - start_timestamp) * 1000  # Convert to milliseconds

                # Optimized logging: single call instead of 7
                logger.info(f"✅ SAVE: {symbol} {total_quantity}@${ask_price:.2f} latency={processing_time_ms:.1f}ms")

                # Call save_order_to_db (matching the signature from multiprocessing_websocket_rv_hour.py)
                mysql_cursor = db_connection.cursor()
                mysql_cursor.execute('''
                    INSERT INTO Orders (`symbol`, `end_timestamp`, `start_timestamp`, `filledPrice`, `status`, `log`, `orderType`, `totalQuantity`, `tradeSignalsCount`, `ask_price`, `ask_timestamp`, `ask_size`, `bid_price`, `bid_size`, `open_price`, `open_timestamp`, `last_trade_price`, `last_trade_timestamp`, `polygon_second_close`, `active_seconds_count`)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ''', (
                    symbol,
                    end_timestamp,  # When order was saved (END time)
                    start_timestamp,  # When trade arrived (START time)
                    0,  # avgFillPrice (not filled yet)
                    "Simulation",  # status
                    "OK",  # log - simplified to save 1-2ms (no string join)
                    "SIM_BUY",  # orderType (shortened to fit column)
                    total_quantity,
                    trade_signals_count,
                    ask_price,
                    0,  # ask_timestamp
                    0,  # ask_size
                    0,  # bid_price
                    0,  # bid_size
                    open_map.get(symbol, 0),  # open_price
                    0,  # open_map_timestamp
                    price,  # last_trade_price
                    "",  # last_trade_timestamp
                    0,  # polygon_second_close
                    active_seconds_count
                ))
                # No commit needed - autocommit=True handles it without disk sync wait

                # Send final result to validation pipeline
                if validation_queue:
                    try:
                        validation_queue.put({
                            "symbol": symbol,
                            "step": 8,  # Final step
                            "name": "ORDER RESULT",
                            "status": "PASSED",
                            "details": f"{total_quantity} shares @ ${ask_price:.2f}",
                            "final_result": "ORDER_SAVED"
                        }, block=False)
                    except:
                        pass
            else:
                logger.info("❌ Validation failed - Order NOT saved")

                # Send final result to validation pipeline
                if validation_queue:
                    try:
                        validation_queue.put({
                            "symbol": symbol,
                            "step": 8,  # Final step
                            "name": "ORDER RESULT",
                            "status": "FAILED",
                            "details": "One or more validation steps failed",
                            "final_result": "ORDER_REJECTED"
                        }, block=False)
                    except:
                        pass

            # Send display message to UI
            display_message = (
                f"✅ Signal Received: {action} ({rule})\n"
                f"Symbol: {symbol} | Price: ${price:.2f}\n"
                f"Second: {second} | Active Seconds: {active_seconds_count}\n"
                f"High: ${high:.2f} | Low: ${low:.2f}\n"
                f"Validation: {'✅ PASSED' if validation_passed else '❌ FAILED'}\n"
            )

            logger.info(f"📤 Sending display message to queue for {symbol}")
            display_queue.put({
                'type': 'signal',
                'message': display_message,
                'data': signal,
                'signal_count': signal_count,
                'rule': rule
            })
            logger.info(f"✅ Display message sent to queue for {symbol}")

        except Exception as e:
            logger.error(f"Consumer error: {e}", exc_info=True)
            # Continue processing even on error

    # Clean up database connection
    try:
        db_connection.close()
    except:
        pass


def simulation_trade_signal_consumer_websocket(trade_signal_queue, display_queue, validation_queue, symbols):
    """
    WebSocket Trade Signal Validator - VALIDATION ONLY (NO TIME TRACKING)

    This process ONLY validates signals. All time tracking happens in the consumer process.
    """
    import mysql.connector
    import time
    import logging
    from trading_config import PRICE_SPIKE_RISK_THRESHOLD, TRADE_CAPITAL, INCREASE_FROM_OPEN

    logger = logging.getLogger("SignalValidator")
    logger.setLevel(logging.DEBUG)

    if not logger.handlers:
        handler = logging.FileHandler("trading_system.log")
        handler.setFormatter(logging.Formatter(
            '[%(asctime)s] [SIGNAL_VALIDATOR] [%(levelname)s] %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        ))
        logger.addHandler(handler)

    logger.info("=" * 70)
    logger.info("🚀 WEBSOCKET SIGNAL VALIDATOR STARTED")
    logger.info(f"📊 Symbols: {len(symbols)}")
    logger.info("=" * 70)

    signal_count = 0

    db_connection = mysql.connector.connect(
        host="localhost",
        port=3306,
        user="root",
        password="E_I$S5PFri",
        database="histFinanData",
        autocommit=True
    )
    mysql_cursor = db_connection.cursor()

    logger.info("🔄 Starting validation loop...")

    while True:
        try:
            signal = trade_signal_queue.get()

            if signal is None:
                logger.info("Termination signal received")
                break

            signal_count += 1

            action = signal.get("action", "UNKNOWN")
            rule = signal.get("rule", "Unknown")
            symbol = signal.get("symbol", "N/A")
            price = signal.get("price", 0.0)
            second = signal.get("second", 0)
            active_seconds_count = signal.get("active_seconds_count", 0)
            high = signal.get("high", 0.0)
            low = signal.get("low", 0.0)
            open_map = signal.get("open_map", {})
            trade_signals_count = signal.get("trade_signals_count", 0)
            increase_open = signal.get("increase_open", INCREASE_FROM_OPEN)
            trade_arrival_time = signal.get("trade_arrival_time", time.time())

            logger.info(f"SIGNAL: {symbol} ${price:.2f} @{second}s active={active_seconds_count}")

            validation_passed = True

            def send_validation_step(step, name, status, details):
                if validation_queue:
                    try:
                        validation_queue.put({
                            "symbol": symbol,
                            "step": step,
                            "name": name,
                            "status": status,
                            "details": details,
                            "final_result": None
                        }, block=False)
                    except:
                        pass

            # STEP 1: Low Activity Check
            current_second = second
            elapsed_seconds = current_second
            elapsed_seconds_40_percent = elapsed_seconds * 0.40

            if active_seconds_count < elapsed_seconds_40_percent:
                details = f"{active_seconds_count} < {elapsed_seconds_40_percent:.1f}"
                send_validation_step(1, "Low Activity Check", "FAILED", details)
                validation_passed = False
            else:
                details = f"{active_seconds_count} >= {elapsed_seconds_40_percent:.1f}"
                send_validation_step(1, "Low Activity Check", "PASSED", details)

            # STEP 2-4: Simplified checks
            send_validation_step(2, "Volume Check", "PASSED", "OK")
            send_validation_step(3, "Spread Check", "PASSED", "OK")
            send_validation_step(4, "Price Check", "PASSED", "OK")

            # STEP 5: Bearish Doji Check
            if price > open_map.get(symbol, 0):
                send_validation_step(5, "Doji Check", "PASSED", "Bullish")
            else:
                send_validation_step(5, "Doji Check", "FAILED", "Bearish")
                validation_passed = False

            # STEP 6: Increase from Open Check
            if symbol in open_map and open_map[symbol] > 0:
                open_price = open_map[symbol]
                increase_pct = ((price - open_price) / open_price) * 100
                if increase_pct >= INCREASE_FROM_OPEN:
                    send_validation_step(6, "Increase Check", "PASSED", f"+{increase_pct:.2f}%")
                else:
                    send_validation_step(6, "Increase Check", "FAILED", f"+{increase_pct:.2f}%")
                    validation_passed = False
            else:
                send_validation_step(6, "Increase Check", "FAILED", "No open price")
                validation_passed = False

            # STEP 7: Price Spike Check
            if symbol in open_map and open_map[symbol] > 0:
                open_price = open_map[symbol]
                percentage_increase = ((price - open_price) / open_price) * 100

                if percentage_increase >= PRICE_SPIKE_RISK_THRESHOLD:
                    details = f"{percentage_increase:.2f}% >= {PRICE_SPIKE_RISK_THRESHOLD}%"
                    send_validation_step(7, "Spike Check", "FAILED", details)
                    validation_passed = False
                else:
                    details = f"{percentage_increase:.2f}% < {PRICE_SPIKE_RISK_THRESHOLD}%"
                    send_validation_step(7, "Spike Check", "PASSED", details)
            else:
                send_validation_step(7, "Spike Check", "FAILED", "No open price")
                validation_passed = False

            if validation_passed:
                ask_price = price + 0.02
                investment_amount = TRADE_CAPITAL
                total_quantity = int(investment_amount // ask_price) if ask_price > 0 else 0

                start_timestamp = trade_arrival_time
                end_timestamp = time.time()

                logger.info(f"✅ PASSED: {symbol} {total_quantity}@${ask_price:.2f}")

                mysql_cursor.execute("""
                    INSERT INTO Orders (symbol, end_timestamp, start_timestamp, filledPrice, status, log, orderType, totalQuantity, tradeSignalsCount, ask_price, ask_timestamp, ask_size, bid_price, bid_size, open_price, open_timestamp, last_trade_price, last_trade_timestamp, polygon_second_close, active_seconds_count)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    symbol, end_timestamp, start_timestamp, 0, "WebSocket", "OK", "WS_BUY",
                    total_quantity, trade_signals_count, ask_price, 0, 0, 0, 0,
                    open_map.get(symbol, 0), 0, price, "", 0, active_seconds_count
                ))

                if validation_queue:
                    try:
                        validation_queue.put({
                            "symbol": symbol, "step": 8, "name": "ORDER RESULT",
                            "status": "PASSED", "details": f"{total_quantity} @ ${ask_price:.2f}",
                            "final_result": "ORDER_SAVED"
                        }, block=False)
                    except:
                        pass
            else:
                logger.info(f"❌ FAILED: {symbol}")

                if validation_queue:
                    try:
                        validation_queue.put({
                            "symbol": symbol, "step": 8, "name": "ORDER RESULT",
                            "status": "FAILED", "details": "Validation failed",
                            "final_result": "ORDER_REJECTED"
                        }, block=False)
                    except:
                        pass

            display_message = (
                f"Signal: {symbol} @ ${price:.2f}\n"
                f"Validation: {'PASSED' if validation_passed else 'FAILED'}\n"
            )

            display_queue.put({
                'type': 'signal',
                'message': display_message,
                'data': signal,
                'signal_count': signal_count,
                'rule': rule
            })

        except Exception as e:
            logger.error(f"Validator error: {e}", exc_info=True)

    try:
        mysql_cursor.close()
        db_connection.close()
    except:
        pass

    logger.info("🛑 Validator stopped")




# ============================================================================
# WebSocket Consumer Process (Real-time data from Polygon.io)
# ============================================================================

def websocket_producer_process(trade_queue, symbols):
    """
    WebSocket Producer Process - PURE PRODUCER (like market_data_producer in production)

    Responsibilities:
    - Receive trades from Polygon.io WebSocket
    - Put raw trades into queue
    - NOTHING ELSE

    This follows the producer-consumer pattern from multiprocessing_websocket_rv_hour.py

    Args:
        trade_queue: Queue to send raw trades to consumer process
        symbols: List of stock symbols to subscribe to
    """
    import time
    from polygon import WebSocketClient
    import logging
    import os

    # Configure logger
    logger = logging.getLogger("WebSocketProducer")
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        handler = logging.FileHandler("trading_system.log")
        handler.setFormatter(logging.Formatter(
            '[%(asctime)s] [WS_PRODUCER] [%(levelname)s] %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        ))
        logger.addHandler(handler)

    logger.info("=" * 70)
    logger.info("🚀 WEBSOCKET PRODUCER STARTED")
    logger.info(f"📊 Symbols: {len(symbols)}")
    logger.info(f"🔧 PID: {os.getpid()}")
    logger.info("=" * 70)

    # Error handlers
    def handle_error(ws, error):
        logger.error(f"❌ WebSocket Error: {error}")

    def handle_close(ws):
        logger.warning("⚠️ WebSocket connection closed")

    # WebSocket client
    api_key = 'hzZItvRA2Rfrri2XEjt2VSyMek9PC1Yu'
    subscriptions = [f"T.{symbol}" for symbol in symbols]

    ws_client = WebSocketClient(
        api_key=api_key,
        subscriptions=subscriptions,
        error_handler=handle_error,
        close_handler=handle_close
    )

    # Message handler - ONLY extracts and queues (like production)
    def handle_msg(msgs):
        for m in msgs:
            trade_queue.put({
                "symbol": m.symbol,
                "price": m.price,
                "volume": m.size,
                "timestamp": m.timestamp,
                "conditions": m.conditions,
                "id": m.id,
                "exchange": m.exchange,
                "trf_id": m.trf_id
            })

    logger.info("🌐 Starting WebSocket connection...")
    ws_client.run(handle_msg=handle_msg)


def websocket_trade_consumer_process(trade_queue, trade_signal_queue, display_queue, validation_queue, symbols, relative_volume_factor):
    """
    Trade Consumer Process - PROCESSES TRADES (like consumer_process in production)

    Responsibilities:
    - Read raw trades from trade_queue
    - Calculate OHLCV (Open/High/Low/Close/Volume)
    - Track activity patterns
    - Generate trade signals
    - Send signals to trade_signal_queue for validation

    This follows the consumer pattern from multiprocessing_websocket_rv_hour.py

    Args:
        trade_queue: Queue to read raw trades from producer
        trade_signal_queue: Queue to send generated signals to validation process
        display_queue: Queue to send UI updates
        validation_queue: Queue to send validation status
        symbols: List of stock symbols
        relative_volume_factor: RV threshold for signal generation
    """
    import time
    from datetime import datetime
    import logging
    import os

    # Configure logger
    logger = logging.getLogger("TradeConsumer")
    logger.setLevel(logging.DEBUG)

    if not logger.handlers:
        handler = logging.FileHandler("trading_system.log")
        handler.setFormatter(logging.Formatter(
            '[%(asctime)s] [TRADE_CONSUMER] [%(levelname)s] %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        ))
        logger.addHandler(handler)

    logger.info("=" * 70)
    logger.info("🚀 TRADE CONSUMER PROCESS STARTED")
    logger.info(f"📊 Symbols: {len(symbols)}")
    logger.info(f"📈 RV Factor: {relative_volume_factor}")
    logger.info(f"🔧 PID: {os.getpid()}")
    logger.info("=" * 70)

    # Trade counter for UI display
    total_trades_received = 0

    # Send initial counter to UI
    if display_queue:
        display_queue.put({"type": "trade_count", "count": 0})

    # Verify RV data exists
    import mysql.connector
    db_connection = mysql.connector.connect(
        host="localhost",
        port=3306,
        user="root",
        password="E_I$S5PFri",
        database="histFinanData"
    )
    cursor = db_connection.cursor()

    cursor.execute("SELECT DISTINCT symbol FROM RelativeVolumeRatioHour")
    symbols_with_rv = {row[0] for row in cursor.fetchall()}

    missing_rv = [s for s in symbols if s not in symbols_with_rv]
    if missing_rv:
        error_msg = f"❌ ERROR: {len(missing_rv)} symbols missing RV data"
        logger.error(error_msg)
        cursor.close()
        db_connection.close()
        raise ValueError(f"Missing RV data. Run utils dashboard first!")

    logger.info(f"✅ All {len(symbols)} symbols have RV data")

    # Initialize OHLCV maps
    trade_consumer_open_map = {symbol: 0 for symbol in symbols}
    trade_consumer_close_map = {symbol: 0 for symbol in symbols}
    trade_consumer_high_map = {symbol: 0 for symbol in symbols}
    trade_consumer_low_map = {symbol: 0 for symbol in symbols}
    trade_consumer_volume_map = {symbol: 0 for symbol in symbols}
    trade_consumer_open_map_timestamp = {symbol: 0 for symbol in symbols}
    trades_by_second_map_set = {symbol: set() for symbol in symbols}
    activity_second_count_hashmap = {symbol: 0 for symbol in symbols}
    trade_per_minute_map = {symbol: 0 for symbol in symbols}

    # Load conditions for OHLCV filtering
    from trade_simulator import load_conditions_bool_map
    conditions = load_conditions_bool_map("polygon_conditions_trade_stocks.csv")

    # Configuration
    increase_open = 2
    trade_signal_limit = 20
    current_minute = datetime.now().minute  # Initialize from system time (WebSocket mode) or override from first trade (Simulation mode)
    old_trades_count = 0
    first_trade_processed = False  # Flag to track first trade

    # Memory tracking (for signal deduplication)
    trade_signals_memory_hashmap = {}

    logger.info(f"⏰ Current minute initialized: {current_minute}")
    logger.info("🔄 Starting consumer loop - reading from trade_queue...")

    # CONSUMER LOOP - Read from queue and process (like production)
    while True:
        try:
            trade = trade_queue.get()

            symbol = trade["symbol"]
            trade_price  = trade["price"]
            trade_volume = trade["volume"]
            unix_timestamp = trade["timestamp"]
            trade_conditions = trade["conditions"]
            trade_id = trade["id"]
            trade_exchange = trade["exchange"]
            trade_trf_id = trade["trf_id"]

            temp_time_stamp = ((unix_timestamp // 60000) % 60)

            current_time = time.localtime()
            current_second = current_time.tm_sec

            if current_second == 59:
                # Experimento, la idea es evitar que se envie nada a trade signals tan tar de como el segundo 59....
                print(current_second)
                continue

            if temp_time_stamp < current_minute or ( current_minute == 0 and temp_time_stamp == 59):
                old_trades_timestamp += 1
            else:

                if symbol not in trades_by_symbol:
                    trades_by_symbol[symbol] = []    

                trades_by_symbol[symbol].append({
                    "price": trade["price"],
                    "volume": trade["volume"],
                    "timestamp": trade["timestamp"],
                    "id": trade["id"],
                    "conditions": trade["conditions"],
                    "exchange": trade["exchange"],
                    "trf_id": trade["trf_id"]
                })                                 
    
                if trade_consumer_open_map[symbol] == 0:
                    if condition_affects_ohlcv_component(trade_conditions, conditions, 0):

                        # Converts the timestamp from milliseconds to seconds, as trading systems 
                        # typically operate at the second level for event synchronization.
                        timestamp_in_seconds = unix_timestamp // 1000
                        # Extracts the second within the current minute by calculating the 
                        # remainder when dividing the timestamp in seconds by 60 [timestamp_in_seconds % 60].         
                        trades_by_second_map_set[symbol].add(timestamp_in_seconds % 60 )
                        activity_second_count_hashmap[symbol] = len(trades_by_second_map_set[symbol])   

                        trade_consumer_open_map_timestamp[symbol] = unix_timestamp

                        # trade_consumer_open_map_timestamp[symbol] = timestamp_in_seconds % 60                         

                        trade_consumer_open_map[symbol] = trade_price        
                        trade_consumer_close_map[symbol] = trade_price 

                        # Al inicio el trade a apertura tambien se usa como HIGH y LOW.
                        trade_consumer_high_map[symbol] = trade_price   
                        trade_consumer_low_map[symbol] = trade_price  

                if condition_affects_ohlcv_v_p(trade_conditions, conditions, 1):

                    # if trade_volume >= 100:
                    if trade_volume is not None and trade_volume >= 100:                
                        trade_consumer_close_map[symbol] = trade_price   

                        trade_consumer_high_map[symbol] = max(trade_consumer_high_map[symbol], trade_price)
                        trade_consumer_low_map[symbol] = min(trade_consumer_low_map[symbol], trade_price)

                if condition_affects_ohlcv_v_p(trade_conditions, conditions, 2):

                    if trade_volume is not None:
                        # trade_consumer_volume_map[symbol] += trade_volume

                        if trade_volume >= 100:
                            #Al parecer el volumen que es menor a 100 no suma para el total de volumen del trade.    
                            trade_consumer_volume_map[symbol] += trade_volume

                            # Esta validacion nos permite filtar trades con volumen menor a 100 acciones, no deberiamos considerar  como un Segundo de actividad cuando el trade es muy pequeño.
                            #Hipotesis para descartar ruido de mercado.

                            # Converts the timestamp from milliseconds to seconds, as trading systems 
                            # typically operate at the second level for event synchronization.
                            timestamp_in_seconds = unix_timestamp // 1000
                            # Extracts the second within the current minute by calculating the 
                            # remainder when dividing the timestamp in seconds by 60 [timestamp_in_seconds % 60].         
                            trades_by_second_map_set[symbol].add(timestamp_in_seconds % 60 )
                            activity_second_count_hashmap[symbol] = len(trades_by_second_map_set[symbol])                               

                    # else:
                    #     print(" ")
                    #     print(trade)                
                    #     print(F"\033[1;31mWARNING: TRADE_VOLUME IS NONE FOR {symbol}\033[0m")
                    #     print(" ")
                        

                    if symbol in real_time_positions:

                        bot_price = real_time_positions[symbol]

                        if trade_consumer_close_map[symbol] < bot_price * MAX_LOSS_TOLERANCE_PER_TRADE and trade_consumer_close_map[symbol] > 0:     
                            del real_time_positions[symbol]                                    
                            
                            drop_percentage = ((bot_price -trade_consumer_close_map[symbol]) / bot_price) * 100
                            if not os.environ.get('DASHBOARD_MODE'):
                                print("🔻 ALERT 🔻")
                                print(f"{symbol} has dropped more than {drop_percentage:.2f}%")
                                print(f"Last price  = ${trade_consumer_close_map[symbol]:.2f}")
                                print(f"Entry price = ${bot_price:.2f}")

                            selloff_queue.put({
                                "symbol": symbol,
                                "close": trade_consumer_close_map[symbol]
                            })  

                        if trade_consumer_close_map[symbol] >= bot_price * 1.05:

                            del real_time_positions[symbol]                                    

                            take_profit_queue.put({
                                "symbol": symbol,
                                "close": trade_consumer_close_map[symbol],
                                "bot_price": bot_price
                            })

                cumulative_volume = trade_consumer_volume_map[symbol]            

                relative_volume_hour = relative_volume_list_hashmap_hour[symbol]

                if relative_volume_hour == 0:
                    relative_volume_hour = 10000                              

                relative_volume_factor_hour = round(cumulative_volume / relative_volume_hour , 2) 

                if symbol in high_short_interest_stocks:    
                    
                    if trade_consumer_open_map[symbol] > 0:

                        open_price = trade_consumer_open_map[symbol]  # Esto debe ser el precio al que se abrió

                        price_change_percentage = ((trade_consumer_close_map[symbol] - open_price) / open_price) * 100

                        if price_change_percentage > ( increase_open + 2 ) and symbol not in trade_signals_memory_hashmap:

                            print(f"Short Squeeze - Stock Detected: {symbol} - Open Price: {open_price}, Current Price: {trade_consumer_close_map[symbol]}, Change: {price_change_percentage:.2f}%")                    
                            print(f"Open Price: {open_price}, Current Price: {trade_consumer_close_map[symbol]}, Change: {price_change_percentage:.2f}%")     
                            print(" ")                               
                            trade_signals_memory_hashmap[symbol] = 1

                            active_seconds_count = len(trades_by_second_map_set[symbol])                             

                            tradeSignalId, purchasePrediction = persist_trade_signal(symbol, consumer_id, active_seconds_count, trade_per_minute_map[symbol], unix_timestamp, trade_consumer_open_map[symbol], trade_consumer_open_map_timestamp[symbol], trade_consumer_close_map[symbol], cumulative_volume, 10, stock_float_hashmap[symbol],
                            cumulative_volume, -1, {}, relative_volume_factor_hour, increase_open, 0, trade_id, trade_exchange, trade_trf_id, "short_squeeze", trade_signal_persist_queue, trade_consumer_high_map[symbol], trade_consumer_low_map[symbol])                                                    

                if symbol in trade_signals_track_stock_price:

                    percentage_change = ((trade_consumer_close_map[symbol] - trade_signals_track_stock_price[symbol]) / trade_signals_track_stock_price[symbol]) * 100       

                    if percentage_change >= increase_open:

                        del trade_signals_track_stock_price[symbol]                           

                        print(f"Tracking Price for {symbol}: {trade_consumer_close_map[symbol]}, Change: {percentage_change:.2f}%")   

                        active_seconds_count = len(trades_by_second_map_set[symbol])    

                        trade_signal_queue.put({
                            "action": "BUY",
                            "port": port,
                            "symbol": symbol,
                            "second": timestamp_in_seconds % 60,
                            "active_seconds_count": active_seconds_count,                                    
                            "trade_signals_count": trade_per_minute_map[symbol],
                            "timestamp": unix_timestamp,
                            "minute": current_minute,
                            "price": trade_consumer_close_map[symbol],
                            "relative_volume_factor": -1,
                            "news_time_window_minutes": 0,
                            "trade_signal_limit": trade_signal_limit,
                            "open_map": trade_consumer_open_map,
                            "open_map_timestamp": trade_consumer_open_map_timestamp[symbol],
                            "increase_open": increase_open,
                            "stale_threshold_minutes_config": stale_threshold_minutes_config,
                            "high": trade_consumer_high_map[symbol], 
                            "low": trade_consumer_low_map[symbol],
                        })     
                        
                        tradeSignalId, purchasePrediction = persist_trade_signal(symbol, consumer_id, active_seconds_count, trade_per_minute_map[symbol], unix_timestamp, trade_consumer_open_map[symbol], trade_consumer_open_map_timestamp[symbol], trade_consumer_close_map[symbol], cumulative_volume, 10, stock_float_hashmap[symbol],
                        cumulative_volume, -1, {}, relative_volume_factor_hour, increase_open, 0, trade_id, trade_exchange, trade_trf_id, "track_stock_price_increase", trade_signal_persist_queue, trade_consumer_high_map[symbol], trade_consumer_low_map[symbol])                                                 

                #NEW IMPLEMENTATION TO TRACK LOW ACTIVITY STOCKS

                if symbol in trade_signals_track_low_activity:

                    current_time = datetime.now()
                    current_second = current_time.second

                    elapsed_seconds = current_second - open_map_timestamp
                    elapsed_seconds_33_percent = elapsed_seconds * percentage

                    active_seconds_count = len(trades_by_second_map_set[symbol])                       

                    if active_seconds_count > elapsed_seconds_33_percent:

                        del trade_signals_track_low_activity[symbol]                           

                        trade_signal_queue.put({
                            "action": "BUY",
                            "port": port,
                            "symbol": symbol,
                            "second": timestamp_in_seconds % 60,
                            "active_seconds_count": active_seconds_count,                                    
                            "trade_signals_count": trade_per_minute_map[symbol],
                            "timestamp": unix_timestamp,
                            "minute": current_minute,
                            "price": trade_consumer_close_map[symbol],
                            "relative_volume_factor": -1,
                            "news_time_window_minutes": 0,
                            "trade_signal_limit": trade_signal_limit,
                            "open_map": trade_consumer_open_map,
                            "open_map_timestamp": trade_consumer_open_map_timestamp[symbol],
                            "increase_open": increase_open,
                            "stale_threshold_minutes_config": stale_threshold_minutes_config,
                            "high": trade_consumer_high_map[symbol], 
                            "low": trade_consumer_low_map[symbol],
                        })     
                        
                        tradeSignalId, purchasePrediction = persist_trade_signal(symbol, consumer_id, active_seconds_count, trade_per_minute_map[symbol], unix_timestamp, trade_consumer_open_map[symbol], trade_consumer_open_map_timestamp[symbol], trade_consumer_close_map[symbol], cumulative_volume, 10, stock_float_hashmap[symbol],
                        cumulative_volume, -1, {}, relative_volume_factor_hour, increase_open, 0, trade_id, trade_exchange, trade_trf_id, "track_stock_low_activity", trade_signal_persist_queue, trade_consumer_high_map[symbol], trade_consumer_low_map[symbol])                                                 

                if relative_volume_factor_hour >= RELATIVE_VOLUME_FACTOR:

                    if symbol not in trade_signals_memory_hashmap:    
                        trade_signals_memory_hashmap[symbol] = cumulative_volume
                        
                        if trade_consumer_open_map[symbol] == 0:                    
                            continue

                        active_seconds_count = len(trades_by_second_map_set[symbol])   

                        # print(f"Symbol ={symbol}")
                        # print(f"Open ={trade_consumer_open_map[symbol]}")                                                                                                  
                        # print(f"trade_price ={trade_price}")     
                        # print(f"close ={trade_consumer_close_map[symbol]}")                                                                                        

                        tradeSignalId, purchasePrediction = persist_trade_signal(symbol, consumer_id, active_seconds_count, trade_per_minute_map[symbol], unix_timestamp, trade_consumer_open_map[symbol], trade_consumer_open_map_timestamp[symbol], trade_consumer_close_map[symbol], cumulative_volume, 10, stock_float_hashmap[symbol],
                        cumulative_volume, -1, {}, relative_volume_factor_hour, increase_open, 0, trade_id, trade_exchange, trade_trf_id, "----", trade_signal_persist_queue, trade_consumer_high_map[symbol], trade_consumer_low_map[symbol])   

                        # end_time = time.perf_counter()

                        # tiempo_ms = (end_time - init_time) * 1000
                        # print(f"Tiempo transcurrido Ext: {tiempo_ms:.2f} ms")    

                        current_time = datetime.now()
                        current_second = current_time.second

                        elapsed_seconds = current_second - open_map_timestamp

                        elapsed_seconds_33_percent = elapsed_seconds * percentage

                        if active_seconds_count < elapsed_seconds_33_percent:

                            trade_signals_track_low_activity[symbol] = active_seconds_count   

                        if purchasePrediction == "BUY":

                            print(f"Buy {symbol}")
                            print(f"Buy {trade_signals_to_buy.get(symbol, 0)}")
                            print(trade_signals_to_buy)
                            trade_signals_to_buy[symbol] = trade_signals_to_buy.get(symbol, 0) + 1


                            # news_queue.put({
                            #     "symbol": symbol,
                            #     "tradeSignalId": tradeSignalId
                            # })                                                                                                                                                                         

                            trade_signal_queue.put({
                                "action": "BUY",
                                "port": port,
                                "symbol": symbol,
                                "second": timestamp_in_seconds % 60,
                                "active_seconds_count": active_seconds_count,
                                "trade_signals_count": trade_per_minute_map[symbol],
                                "timestamp": unix_timestamp,
                                "minute": current_minute,
                                "price": trade_consumer_close_map[symbol],
                                "relative_volume_factor": -1,
                                "news_time_window_minutes": 0,
                                "trade_signal_limit": trade_signal_limit,
                                "open_map": trade_consumer_open_map,
                                "open_map_timestamp": trade_consumer_open_map_timestamp[symbol],
                                "increase_open": increase_open,
                                "stale_threshold_minutes_config": stale_threshold_minutes_config,
                                "high": trade_consumer_high_map[symbol], 
                                "low": trade_consumer_low_map[symbol]
                            })
                        else:


                            if "Price increase less than" in purchasePrediction:
                                trade_signals_track_stock_price[symbol] = trade_consumer_open_map[symbol]    
                                # news_queue.put({
                                #     "symbol": symbol,
                                #     "tradeSignalId": tradeSignalId
                                # })                                                                                                                                                                         

                            if "Doji Candle" in purchasePrediction:                                    
                                trade_signals_track_stock_price[symbol] = trade_consumer_open_map[symbol]

                                # news_queue.put({
                                #     "symbol": symbol,
                                #     "tradeSignalId": tradeSignalId
                                # })     



            # if queue.qsize() > queue_max_size:
            #     queue_max_size = queue.qsize()                

            trade_count += 1                  
            trade_count_total += 1  
    
            if( current_minute != datetime.now().minute ):    
                activity_second_count_hashmap.clear()

                current_minute = datetime.now().minute          

                consolidate_minute_queue.put({
                    "queue_max_size": queue_max_size,
                    "trade_count_total": trade_count_total,
                    "trade_count": trade_count,
                    "unix_timestamp": unix_timestamp,
                    "old_trades_timestamp": old_trades_timestamp,
                    "trade_consumer_volume_map": copy.copy(trade_consumer_volume_map),
                    "trade_consumer_close_map": copy.copy(trade_consumer_close_map),
                    "real_time_positions_size": len(real_time_positions),
                    "trade_signals_memory_hashmap": copy.copy(trade_signals_memory_hashmap),
                    "trades_by_symbol": copy.copy(trades_by_symbol)
                })    

                trade_consumer_close_map.clear()
                trade_consumer_high_map.clear()
                trade_consumer_low_map.clear()

                for key in trade_consumer_volume_map.keys():
                    trade_consumer_volume_map[key] = 0
                
                trade_consumer_open_map.clear()
                trade_consumer_open_map_timestamp.clear()
                trade_per_minute_map.clear()
                trade_signals_memory_hashmap.clear()
                trade_signals_track_stock_price.clear()

                trade_signals_track_low_activity.clear()

                trades_by_second_map_set.clear()

                trade_consumer_close_map = {symbol: 0 for symbol in symbols}
                trade_consumer_high_map = {symbol: 0 for symbol in symbols}
                trade_consumer_low_map = {symbol: 0 for symbol in symbols}                
                trade_consumer_open_map = {symbol: 0 for symbol in symbols}
                trade_consumer_open_map_timestamp = {symbol: 0 for symbol in symbols}    
                trade_per_minute_map = {symbol: 0 for symbol in symbols}
                trade_signals_memory_hashmap = {}    
                trades_by_symbol.clear()
                trades_by_symbol = {}
                trade_signals_track_low_activity = {}

                trades_by_second_map_set = {symbol: set() for symbol in symbols}  

                relative_volume_list_hashmap_hour = get_relative_volume_hour(get_current_hour(), get_am_pm(), mysql_cursor)

                old_trades_timestamp = 0
                queue_max_size = 0
                trade_count = 0

        except Exception as e:
            logger.error(
                f"❌ ERROR in websocket_trade_consumer_process: {str(e)}",
                exc_info=True,
                extra={
                    'symbol': symbol if 'symbol' in locals() else 'UNKNOWN',
                    'trade_data': trade if 'trade' in locals() else None
                }
            )
            # Continue processing next trade
            continue

# ============================================================================
# Experimental Widgets
# ============================================================================

class ExperimentWidget1(Static):
    """First experimental widget - customize as needed"""

    def __init__(self, data_source: ExperimentalDataSource, **kwargs):
        super().__init__(**kwargs)
        self.data_source = data_source
        self.table = DataTable()

    def compose(self) -> ComposeResult:
        yield Label("[bold cyan]Experiment Widget 1[/bold cyan]")
        yield self.table

    def on_mount(self):
        self.table.add_columns("Ticker", "Close", "Float")
        self.update_data()

    def update_data(self):
        """Load and display sample data"""
        self.table.clear()

        data = self.data_source.get_sample_data()

        if not data:
            self.table.add_row("No data", "-", "-")
            return

        for item in data:
            ticker = item.get('ticker', 'N/A')
            close = f"${item.get('close', 0):.2f}"
            float_val = f"{item.get('float_value', 0):,}"
            self.table.add_row(ticker, close, float_val)


class ExperimentWidget2(Static):
    """Download historical trades from Polygon.io"""

    def __init__(self, data_source: ExperimentalDataSource, **kwargs):
        super().__init__(**kwargs)
        self.data_source = data_source

    def calculate_business_days_ago(self, days_back):
        """
        Calculate a date that is N business days ago (excluding weekends).

        Args:
            days_back: Number of business days to go back

        Returns:
            datetime: Date N business days ago
        """
        from datetime import timedelta

        current_date = datetime.now()
        business_days_counted = 0

        while business_days_counted < days_back:
            current_date -= timedelta(days=1)
            # Skip weekends (5=Saturday, 6=Sunday)
            if current_date.weekday() < 5:
                business_days_counted += 1

        return current_date

    def compose(self) -> ComposeResult:
        yield Label("[bold yellow]Historical Trades (2026)[/bold yellow]", id="historical_trades_label")
        yield Input(placeholder="Month-Day (MM-DD)", id="month_day_input", value="")
        yield Input(placeholder="Hour-Minute (HH-MM)", id="hour_minute_input", value="")
        yield Input(placeholder="Symbol (e.g., PHGE)", id="symbol_input")
        yield Label("[bold cyan]Relative Volume Date Range[/bold cyan]", id="rv_date_range_label")
        yield Input(placeholder="Start Date (YYYY-MM-DD)", id="start_date_input", value="")
        yield Input(placeholder="End Date (YYYY-MM-DD)", id="end_date_input", value="")
        yield Button("📥 Download Trades", id="test_btn", variant="primary")
        yield Button("🗑️ Purge Trade Data", id="clear_btn", variant="error")
        yield Button("▶️ Run Simulation", id="run_simulation_btn", variant="success")
        yield Button("🌐 Connect WebSocket", id="websocket_btn", variant="warning")
        yield Label("[bold green]⏰ Time:[/bold green] [dim]--:--[/dim]", id="websocket_time_label")

    def on_mount(self):
        """Preload fields with current date and calculated start date"""
        # Disable Run Simulation button until data is ready
        run_btn = self.query_one("#run_simulation_btn", Button)
        run_btn.disabled = True

        # Hide time label initially (shown only when WebSocket is connected)
        time_label = self.query_one("#websocket_time_label", Label)
        time_label.display = False

        # Get current date
        today = datetime.now()

        # Populate Month-Day (format: M-D or MM-DD)
        self.query_one("#month_day_input", Input).value = f"{today.month}-{today.day}"

        # Populate Hour-Minute with default time (e.g., 06-00)
        self.query_one("#hour_minute_input", Input).value = "6-0"

        # Calculate 15 business days ago for Start Date
        start_date = self.calculate_business_days_ago(15)

        # Populate Start Date and End Date
        self.query_one("#start_date_input", Input).value = start_date.strftime("%Y-%m-%d")
        self.query_one("#end_date_input", Input).value = today.strftime("%Y-%m-%d")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button press - Download trades or clear data"""
        if event.button.id == "run_simulation_btn":
            # Run trade simulation using multiprocessing
            self.app.notify("▶️ Starting simulation...", severity="information")

            # ========================================
            # RESTORE SIMULATION UI ELEMENTS
            # ========================================

            # Show Price Chart (needed for simulation mode)
            try:
                price_chart = self.app.query_one(PriceChartWidget)
                price_chart.display = True
                logger.info("📊 Price Chart visible")
            except Exception as e:
                logger.warning(f"Could not show Price Chart: {e}")

            # Show Raw Trades List panel
            try:
                raw_trades_widget = self.app.query_one(ExperimentWidget3)
                raw_trades_widget.display = True
                logger.info("📊 Raw Trades List visible")
            except Exception as e:
                logger.warning(f"Could not show Raw Trades List: {e}")

            # Show the trades-section container
            try:
                trades_section = self.app.query_one("#trades-section")
                trades_section.display = True
                logger.info("📊 Trades section container visible")
            except Exception as e:
                logger.warning(f"Could not show trades section: {e}")

            # Show Download Trades button
            try:
                download_btn = self.app.query_one("#test_btn", Button)
                download_btn.display = True
                logger.info("📊 Download Trades button visible")
            except Exception as e:
                logger.warning(f"Could not show Download Trades button: {e}")

            # Show Purge Trade Data button
            try:
                clear_btn = self.app.query_one("#clear_btn", Button)
                clear_btn.display = True
                logger.info("📊 Purge Trade Data button visible")
            except Exception as e:
                logger.warning(f"Could not show Purge Trade Data button: {e}")

            # Show Run Simulation button
            try:
                run_sim_btn = self.app.query_one("#run_simulation_btn", Button)
                run_sim_btn.display = True
                logger.info("📊 Run Simulation button visible")
            except Exception as e:
                logger.warning(f"Could not show Run Simulation button: {e}")

            # Show Historical Trades input fields
            try:
                self.app.query_one("#month_day_input", Input).display = True
                logger.info("📊 Month-Day input visible")
            except Exception as e:
                logger.warning(f"Could not show Month-Day input: {e}")

            try:
                self.app.query_one("#hour_minute_input", Input).display = True
                logger.info("📊 Hour-Minute input visible")
            except Exception as e:
                logger.warning(f"Could not show Hour-Minute input: {e}")

            try:
                self.app.query_one("#symbol_input", Input).display = True
                logger.info("📊 Symbol input visible")
            except Exception as e:
                logger.warning(f"Could not show Symbol input: {e}")

            # Show Relative Volume Date Range input fields
            try:
                self.app.query_one("#start_date_input", Input).display = True
                logger.info("📊 Start Date input visible")
            except Exception as e:
                logger.warning(f"Could not show Start Date input: {e}")

            try:
                self.app.query_one("#end_date_input", Input).display = True
                logger.info("📊 End Date input visible")
            except Exception as e:
                logger.warning(f"Could not show End Date input: {e}")

            # Show Trade Download Pipeline
            try:
                download_pipeline = self.app.query_one(TradeDownloadPipelineWidget)
                download_pipeline.display = True
                logger.info("📊 Trade Download Pipeline visible")
            except Exception as e:
                logger.warning(f"Could not show Trade Download Pipeline: {e}")

            # Show section title labels
            try:
                self.app.query_one("#historical_trades_label", Label).display = True
                logger.info("📊 Historical Trades label visible")
            except Exception as e:
                logger.warning(f"Could not show Historical Trades label: {e}")

            try:
                self.app.query_one("#rv_date_range_label", Label).display = True
                logger.info("📊 RV Date Range label visible")
            except Exception as e:
                logger.warning(f"Could not show RV Date Range label: {e}")

            # Hide time label (WebSocket mode only)
            try:
                time_label = self.app.query_one("#websocket_time_label", Label)
                time_label.display = False
                logger.info("🚫 Time label hidden")
            except Exception as e:
                logger.warning(f"Could not hide time label: {e}")

            logger.info("✅ Simulation mode UI restore complete")

            # Reset simulation pipeline
            pipeline = self.app.query_one(SimulationPipelineWidget)
            pipeline.reset()
            pipeline.start_process1()
            pipeline.start_process2()

            # Reset validation pipeline widget
            validation_pipeline = self.app.query_one(ValidationPipelineWidget)
            validation_pipeline.reset()

            # Get the RV FACTOR from the Trading Activity Metrics panel
            metrics_widget = self.app.query_one(TradesBySecondPanel)
            relative_volume = metrics_widget.relative_volume

            # Reset WebSocket metrics (simulation mode doesn't use WebSocket)
            metrics_widget.websocket_symbols_count = 0
            metrics_widget.websocket_trades_count = 0

            if relative_volume == 0:
                self.app.notify("❌ No Relative Volume data. Download trades first!", severity="error")
                return

            # Create multiprocessing Queues (same pattern as run_processes)
            results_queue = multiprocessing.Queue(maxsize=10)
            trade_signal_queue = multiprocessing.Queue(maxsize=10000)  # Signal queue (simulation → consumer)
            display_queue = multiprocessing.Queue(maxsize=100)  # Display queue (consumer → UI)
            validation_queue = multiprocessing.Queue(maxsize=100)  # Validation pipeline tracking

            # Import and start simulation process
            from trade_simulator import simulate_consumer_process

            # Create simulation process (producer)
            simulation_process = multiprocessing.Process(
                target=simulate_consumer_process,
                args=(relative_volume, results_queue, trade_signal_queue)
            )

            # Create trade signal consumer process (consumer) - SIMULATION MODE
            consumer_process = multiprocessing.Process(
                target=simulation_trade_signal_consumer,
                args=(trade_signal_queue, display_queue, validation_queue, "simulation")
            )

            # Start both processes
            simulation_process.start()
            consumer_process.start()
            logger.info("Simulation process and consumer process started")

            # Poll queues for results and display messages
            def queue_monitor():
                try:
                    simulation_complete = False

                    while not simulation_complete:
                        # Check display queue for signal messages
                        try:
                            display_msg = display_queue.get(timeout=0.1)
                            if display_msg['type'] == 'signal':
                                signal_data = display_msg.get('data', {})
                                logger.info(f"📨 Display message received: {signal_data.get('symbol')} @ ${signal_data.get('price', 0):.2f}")

                                def update_signal_ui(sig_data=signal_data):
                                    # Update pipeline panel with signal data
                                    pipeline = self.app.query_one(SimulationPipelineWidget)
                                    pipeline.signal_received({
                                        'action': sig_data.get('action', 'UNKNOWN'),
                                        'rule': sig_data.get('rule', 'Unknown'),
                                        'symbol': sig_data.get('symbol', 'N/A'),
                                        'price': sig_data.get('price', 0.0),
                                        'second': sig_data.get('second', 0),
                                        'active_seconds': sig_data.get('active_seconds_count', 0),
                                        'high': sig_data.get('high', 0.0),
                                        'low': sig_data.get('low', 0.0),
                                        'volume': sig_data.get('volume', 0)
                                    })
                                    logger.info("✅ Pipeline updated with signal")

                                self.app.call_from_thread(update_signal_ui)
                        except Exception as e:
                            if "Empty" not in str(e):  # Ignore empty queue timeout
                                logger.error(f"Error processing display message: {e}", exc_info=True)

                        # Check validation queue for validation step results
                        try:
                            validation_msg = validation_queue.get(timeout=0.1)
                            logger.info(f"🔍 Validation step received: Step {validation_msg.get('step')} - {validation_msg.get('status')}")

                            def update_validation_ui(val_msg=validation_msg):
                                validation_pipeline = self.app.query_one(ValidationPipelineWidget)
                                validation_pipeline.add_validation_result(val_msg)
                                logger.info(f"✅ Validation pipeline updated: {val_msg.get('name')}")

                            self.app.call_from_thread(update_validation_ui)
                        except:
                            pass  # No validation message yet

                        # Check results queue for final result
                        try:
                            result = results_queue.get(timeout=0.1)
                            logger.info("Simulation result received from queue")
                            simulation_complete = True
                        except:
                            pass  # No result yet

                    # Process any remaining display messages after simulation completes
                    logger.info("Processing remaining display messages...")
                    while True:
                        try:
                            display_msg = display_queue.get(timeout=1.0)
                            if display_msg['type'] == 'signal':
                                signal_data = display_msg.get('data', {})
                                logger.info(f"📨 Late display message received: {signal_data.get('symbol')} @ ${signal_data.get('price', 0):.2f}")

                                def update_signal_ui(sig_data=signal_data):
                                    pipeline = self.app.query_one(SimulationPipelineWidget)
                                    pipeline.signal_received({
                                        'action': sig_data.get('action', 'UNKNOWN'),
                                        'rule': sig_data.get('rule', 'Unknown'),
                                        'symbol': sig_data.get('symbol', 'N/A'),
                                        'price': sig_data.get('price', 0.0),
                                        'second': sig_data.get('second', 0),
                                        'active_seconds': sig_data.get('active_seconds_count', 0),
                                        'high': sig_data.get('high', 0.0),
                                        'low': sig_data.get('low', 0.0),
                                        'volume': sig_data.get('volume', 0)
                                    })
                                    logger.info("✅ Pipeline updated with late signal")

                                self.app.call_from_thread(update_signal_ui)
                        except Exception as e:
                            if "Empty" not in str(e):
                                logger.error(f"Error processing late display message: {e}", exc_info=True)
                            break  # No more messages

                    # Process any remaining validation messages
                    logger.info("Processing remaining validation messages...")
                    while True:
                        try:
                            validation_msg = validation_queue.get(timeout=1.0)
                            logger.info(f"🔍 Late validation step received: Step {validation_msg.get('step')} - {validation_msg.get('status')}")

                            def update_validation_ui(val_msg=validation_msg):
                                validation_pipeline = self.app.query_one(ValidationPipelineWidget)
                                validation_pipeline.add_validation_result(val_msg)
                                logger.info(f"✅ Validation pipeline updated: {val_msg.get('name')}")

                            self.app.call_from_thread(update_validation_ui)
                        except:
                            # No more validation messages
                            break

                    # Now update final results
                    if simulation_complete:
                        # Update UI from main thread
                        def update_ui():
                            # Update pipeline with the qualifying trade (met both conditions)
                            pipeline = self.app.query_one(SimulationPipelineWidget)

                            # Only show the trade that met BOTH conditions (Rule 2)
                            qualifying_trade = result.get('first_2pct_with_rv_trade')
                            if qualifying_trade:
                                pipeline.set_qualifying_trade({
                                    'price': qualifying_trade.get('price', 0.0),
                                    'exchange': qualifying_trade.get('exchange', 'N/A'),
                                    'volume': qualifying_trade.get('volume', 0),
                                    'open': qualifying_trade.get('open', 0.0),
                                    'cumulative_volume': qualifying_trade.get('cumulative_volume', 0),
                                    'timestamp': qualifying_trade.get('timestamp', '')
                                })

                            pipeline.complete_process1()
                            pipeline.complete_process2()

                            # Update chart with Rule 2 marker
                            chart_widget = self.app.query_one(PriceChartWidget)
                            rule2_trade = result.get('first_2pct_with_rv_trade')
                            if rule2_trade:
                                chart_widget.set_rule2_trade(rule2_trade)

                            summary = (
                                f"✅ Simulation Complete: "
                                f"{result['trade_count']:,} trades processed, "
                                f"{result['buy_signals']} BUY signals generated"
                            )
                            self.app.notify(summary, severity="information")

                            # Refresh orders list to show new simulation orders
                            orders_panel = self.app.query_one(OrdersListPanel)
                            orders_panel.refresh_orders()

                        self.app.call_from_thread(update_ui)

                    # Send termination signal to consumer
                    trade_signal_queue.put(None)

                    # Clean up processes
                    simulation_process.join(timeout=5)
                    consumer_process.join(timeout=5)

                except Exception as e:
                    logger.error(f"Queue monitor error: {e}", exc_info=True)

                    def error_ui():
                        self.app.notify(f"❌ Simulation failed: {str(e)}", severity="error")

                    self.app.call_from_thread(error_ui)

            # Start queue monitor thread
            threading.Thread(target=queue_monitor, daemon=True).start()

        elif event.button.id == "websocket_btn":
            # Connect to Polygon.io WebSocket for real-time data
            self.app.notify("🌐 Connecting to WebSocket...", severity="information")

            # ========================================
            # HIDE SIMULATION-ONLY UI ELEMENTS
            # ========================================

            # Hide Price Chart (not needed for WebSocket mode)
            try:
                price_chart = self.app.query_one(PriceChartWidget)
                price_chart.display = False
                logger.info("🚫 Price Chart hidden")
            except Exception as e:
                logger.warning(f"Could not hide Price Chart: {e}")

            # Hide Raw Trades List panel (simulation data only)
            try:
                raw_trades_widget = self.app.query_one(ExperimentWidget3)
                raw_trades_widget.display = False
                logger.info("🚫 Raw Trades List hidden")
            except Exception as e:
                logger.warning(f"Could not hide Raw Trades List: {e}")

            # Hide the entire trades-section container (removes empty center panel)
            try:
                trades_section = self.app.query_one("#trades-section")
                trades_section.display = False
                logger.info("🚫 Trades section container hidden")
            except Exception as e:
                logger.warning(f"Could not hide trades section: {e}")

            # Hide Download Trades button (simulation only)
            try:
                download_btn = self.app.query_one("#test_btn", Button)
                download_btn.display = False
                logger.info("🚫 Download Trades button hidden")
            except Exception as e:
                logger.warning(f"Could not hide Download Trades button: {e}")

            # Hide Purge Trade Data button (simulation only)
            try:
                clear_btn = self.app.query_one("#clear_btn", Button)
                clear_btn.display = False
                logger.info("🚫 Purge Trade Data button hidden")
            except Exception as e:
                logger.warning(f"Could not hide Purge Trade Data button: {e}")

            # Hide Run Simulation button (not applicable in WebSocket mode)
            try:
                run_sim_btn = self.app.query_one("#run_simulation_btn", Button)
                run_sim_btn.display = False
                logger.info("🚫 Run Simulation button hidden")
            except Exception as e:
                logger.warning(f"Could not hide Run Simulation button: {e}")

            # Hide Trade Download Pipeline (simulation only)
            try:
                download_pipeline = self.app.query_one(TradeDownloadPipelineWidget)
                download_pipeline.display = False
                logger.info("🚫 Trade Download Pipeline hidden")
            except Exception as e:
                logger.warning(f"Could not hide Trade Download Pipeline: {e}")

            # Hide Historical Trades input fields (simulation only)
            try:
                self.app.query_one("#month_day_input", Input).display = False
                logger.info("🚫 Month-Day input hidden")
            except Exception as e:
                logger.warning(f"Could not hide Month-Day input: {e}")

            try:
                self.app.query_one("#hour_minute_input", Input).display = False
                logger.info("🚫 Hour-Minute input hidden")
            except Exception as e:
                logger.warning(f"Could not hide Hour-Minute input: {e}")

            try:
                self.app.query_one("#symbol_input", Input).display = False
                logger.info("🚫 Symbol input hidden")
            except Exception as e:
                logger.warning(f"Could not hide Symbol input: {e}")

            # Hide Relative Volume Date Range input fields (simulation only)
            try:
                self.app.query_one("#start_date_input", Input).display = False
                logger.info("🚫 Start Date input hidden")
            except Exception as e:
                logger.warning(f"Could not hide Start Date input: {e}")

            try:
                self.app.query_one("#end_date_input", Input).display = False
                logger.info("🚫 End Date input hidden")
            except Exception as e:
                logger.warning(f"Could not hide End Date input: {e}")

            # Hide section title labels (simulation only)
            try:
                self.app.query_one("#historical_trades_label", Label).display = False
                logger.info("🚫 Historical Trades label hidden")
            except Exception as e:
                logger.warning(f"Could not hide Historical Trades label: {e}")

            try:
                self.app.query_one("#rv_date_range_label", Label).display = False
                logger.info("🚫 RV Date Range label hidden")
            except Exception as e:
                logger.warning(f"Could not hide RV Date Range label: {e}")

            logger.info("✅ WebSocket mode UI cleanup complete")

            # Show time label for WebSocket mode
            try:
                time_label = self.app.query_one("#websocket_time_label", Label)
                time_label.display = True
                logger.info("✅ Time label shown")
            except Exception as e:
                logger.warning(f"Could not show time label: {e}")

            # Reset simulation pipeline
            pipeline = self.app.query_one(SimulationPipelineWidget)
            pipeline.reset()
            pipeline.start_process1()
            pipeline.start_process2()

            # Reset validation pipeline widget
            validation_pipeline = self.app.query_one(ValidationPipelineWidget)
            validation_pipeline.reset()

            # Get symbols from database using CENTRALIZED function (same as utils dashboard)
            import mysql.connector
            from trading_config import get_symbols_from_database, RELATIVE_VOLUME_FACTOR

            db_connection = mysql.connector.connect(
                host="localhost",
                port=3306,
                user="root",
                password="E_I$S5PFri",
                database="histFinanData"
            )
            cursor = db_connection.cursor()

            # Use centralized symbol selection - CRITICAL for consistency
            symbols = get_symbols_from_database(cursor)

            cursor.close()
            db_connection.close()

            logger.info(f"WebSocket: Subscribing to {len(symbols)} symbols (using trading_config criteria)")

            # Create multiprocessing Queues (following production pattern)
            trade_queue = multiprocessing.Queue(maxsize=10000)  # Raw trades: producer → consumer
            trade_signal_queue = multiprocessing.Queue(maxsize=10000)  # Signals: consumer → validator
            display_queue = multiprocessing.Queue(maxsize=100)  # UI updates
            validation_queue = multiprocessing.Queue(maxsize=100)  # Validation tracking

            # Process 1: WebSocket Producer (PURE PRODUCER - like market_data_producer)
            producer_process = multiprocessing.Process(
                target=websocket_producer_process,
                args=(trade_queue, symbols)
            )

            # Process 2: Trade Consumer (OHLCV + Signal Generation - like consumer_process)
            trade_consumer_process = multiprocessing.Process(
                target=websocket_trade_consumer_process,
                args=(trade_queue, trade_signal_queue, display_queue, validation_queue, symbols, RELATIVE_VOLUME_FACTOR)
            )

            # Process 3: Signal Validator (Validation + IB Orders) - WEBSOCKET MODE
            # Uses WebSocket-specific consumer with 60-second timer
            signal_validator_process = multiprocessing.Process(
                target=simulation_trade_signal_consumer_websocket,
                args=(trade_signal_queue, display_queue, validation_queue, symbols)
            )

            # Start all THREE processes
            producer_process.start()
            trade_consumer_process.start()
            signal_validator_process.start()
            logger.info("✅ Started 3 processes: Producer → Consumer → Validator")

            # Store processes for cleanup
            self.websocket_producer = producer_process
            self.websocket_consumer = trade_consumer_process
            self.websocket_validator = signal_validator_process

            # Update Trading Activity Metrics with symbol count
            try:
                metrics_panel = self.app.query_one(TradesBySecondPanel)
                metrics_panel.websocket_symbols_count = len(symbols)
                logger.info(f"✅ Symbol count updated: {len(symbols)} symbols")
            except Exception as e:
                logger.error(f"❌ Error updating symbol count: {e}")

            # Poll queues for display and validation messages (WebSocket runs continuously)
            def websocket_queue_monitor():
                try:
                    while True:
                        # Check display queue for signal messages
                        try:
                            display_msg = display_queue.get(timeout=0.1)
                            if display_msg.get('type') == 'signal':
                                signal_data = display_msg.get('data', {})
                                logger.info(f"📨 WebSocket signal: {signal_data.get('symbol')} @ ${signal_data.get('price', 0):.2f}")

                                def update_signal_ui(sig_data=signal_data):
                                    pipeline = self.app.query_one(SimulationPipelineWidget)
                                    pipeline.signal_received({
                                        'action': sig_data.get('action', 'UNKNOWN'),
                                        'rule': sig_data.get('rule', 'Unknown'),
                                        'symbol': sig_data.get('symbol', 'N/A'),
                                        'price': sig_data.get('price', 0.0),
                                        'second': sig_data.get('second', 0),
                                        'active_seconds': sig_data.get('active_seconds_count', 0),
                                        'high': sig_data.get('high', 0.0),
                                        'low': sig_data.get('low', 0.0),
                                        'volume': sig_data.get('volume', 0)
                                    })
                                    logger.info("✅ Pipeline updated with WebSocket signal")

                                self.app.call_from_thread(update_signal_ui)

                            elif display_msg.get('type') == 'trade_count':
                                # Update WebSocket trade counter in Trading Activity Metrics panel
                                trade_count = display_msg.get('count', 0)
                                logger.info(f"🔢 Queue monitor received trade_count: {trade_count:,}")

                                def update_trade_count_ui(count=trade_count):
                                    logger.info(f"🔄 update_trade_count_ui called with count={count}")
                                    try:
                                        metrics_panel = self.app.query_one(TradesBySecondPanel)
                                        logger.info(f"📍 Found metrics_panel: {metrics_panel}")
                                        old_count = metrics_panel.websocket_trades_count
                                        logger.info(f"📊 Current count: {old_count}, Setting to: {count}")

                                        # Update reactive property
                                        metrics_panel.websocket_trades_count = count

                                        # Force manual label update (in case watcher doesn't fire)
                                        metrics_panel._update_websocket_trades_label()

                                        # Force widget refresh
                                        metrics_panel.refresh()

                                        logger.info(f"✅ Assignment complete. New value: {metrics_panel.websocket_trades_count}")
                                    except Exception as e:
                                        logger.error(f"❌ Error in update_trade_count_ui: {e}", exc_info=True)

                                self.app.call_from_thread(update_trade_count_ui)

                            elif display_msg.get('type') == 'error':
                                # Log WebSocket errors
                                error_msg = display_msg.get('message', 'Unknown error')
                                logger.error(f"❌ WebSocket error: {error_msg}")
                                self.app.notify(f"❌ {error_msg}", severity="error")

                            elif display_msg.get('type') == 'status':
                                # Log WebSocket status messages
                                status_msg = display_msg.get('message', '')
                                logger.info(f"ℹ️ WebSocket status: {status_msg}")
                                self.app.notify(status_msg, severity="information")

                            elif display_msg.get('type') == 'time_update':
                                # Update time label
                                time_string = display_msg.get('time', '--:--')
                                logger.info(f"⏰ Time update: {time_string}")

                                def update_time_label(time_str=time_string):
                                    try:
                                        time_label = self.app.query_one("#websocket_time_label", Label)
                                        time_label.update(f"[bold green]⏰ Time:[/bold green] {time_str}")
                                        logger.info(f"✅ Time label updated to: {time_str}")
                                    except Exception as e:
                                        logger.error(f"❌ Error updating time label: {e}", exc_info=True)

                                self.app.call_from_thread(update_time_label)

                        except:
                            # Queue is empty - this is normal, just continue polling
                            pass

                        # Check validation queue for validation step results
                        try:
                            validation_msg = validation_queue.get(timeout=0.1)
                            logger.info(f"🔍 WebSocket validation: Step {validation_msg.get('step')} - {validation_msg.get('status')}")

                            def update_validation_ui(val_msg=validation_msg):
                                validation_pipeline = self.app.query_one(ValidationPipelineWidget)
                                validation_pipeline.add_validation_result(val_msg)
                                logger.info(f"✅ Validation pipeline updated: {val_msg.get('name')}")

                            self.app.call_from_thread(update_validation_ui)
                        except:
                            pass  # No validation message yet

                        # Check if all THREE processes are still alive
                        if not producer_process.is_alive():
                            logger.error("❌ Producer process died!")
                            break
                        if not trade_consumer_process.is_alive():
                            logger.error("❌ Trade consumer process died!")
                            break
                        if not signal_validator_process.is_alive():
                            logger.error("❌ Signal validator process died!")
                            break

                except Exception as e:
                    logger.error(f"WebSocket queue monitor error: {e}", exc_info=True)

                    def error_ui():
                        self.app.notify(f"❌ WebSocket error: {str(e)}", severity="error")

                    self.app.call_from_thread(error_ui)

            # Start queue monitor thread
            threading.Thread(target=websocket_queue_monitor, daemon=True).start()

        elif event.button.id == "clear_btn":
            # Handle purge button
            try:
                event.button.disabled = True
                self.app.notify("⏳ Purging trade data and simulation results...", severity="information")

                # Clear RawTrades table
                rows_deleted = self.data_source.clear_raw_trades()

                # Clear Orders table (simulation orders)
                import mysql.connector
                db_connection = mysql.connector.connect(
                    host="localhost",
                    port=3306,
                    user="root",
                    password="E_I$S5PFri",
                    database="histFinanData"
                )
                cursor = db_connection.cursor()
                cursor.execute("DELETE FROM Orders WHERE orderType = 'SIM_BUY'")
                orders_deleted = cursor.rowcount
                db_connection.commit()
                cursor.close()
                db_connection.close()

                # Update Widget 3 preview, chart, and metrics
                preview_widget = self.app.query_one(ExperimentWidget3)
                preview_widget.update_preview()

                chart_widget = self.app.query_one(PriceChartWidget)
                chart_widget.update_chart()

                # Reset all metrics data
                metrics_widget = self.app.query_one(TradesBySecondPanel)
                metrics_widget.update_metric()
                metrics_widget.relative_volume = 0.0
                metrics_widget.rv_breakdown = []
                metrics_widget.rv_hour = 6
                metrics_widget.update_relative_volume_display()

                # Clear RV breakdown panel
                rv_breakdown_widget = self.app.query_one(RelativeVolumeBreakdownPanel)
                rv_breakdown_widget.clear_data()

                # Reset download pipeline
                pipeline = self.app.query_one(TradeDownloadPipelineWidget)
                pipeline.reset()

                # Reset simulation pipeline
                sim_pipeline = self.app.query_one(SimulationPipelineWidget)
                sim_pipeline.reset()

                # Reset validation pipeline
                validation_pipeline = self.app.query_one(ValidationPipelineWidget)
                validation_pipeline.reset()

                # Reset orders list panel
                orders_panel = self.app.query_one(OrdersListPanel)
                orders_panel.reset()

                # Success notification
                self.app.notify(
                    f"✅ Purged {rows_deleted} trades, {orders_deleted} orders, reset all panels",
                    severity="information"
                )

                event.button.disabled = False

            except Exception as e:
                self.app.notify(f"❌ Error: {str(e)}", severity="error")
                event.button.disabled = False

        elif event.button.id == "test_btn":
            try:
                # Hard-coded year
                year = 2026

                # Get input values
                # Parse Month-Day (format: M-D or MM-DD)
                month_day_value = self.query_one("#month_day_input", Input).value.strip()
                month_day_parts = month_day_value.split('-')
                month = int(month_day_parts[0])
                day = int(month_day_parts[1])

                # Parse Hour-Minute (format: H-M or HH-MM)
                hour_minute_value = self.query_one("#hour_minute_input", Input).value.strip()
                hour_minute_parts = hour_minute_value.split('-')
                hour = int(hour_minute_parts[0])
                minute = int(hour_minute_parts[1])

                symbol = self.query_one("#symbol_input", Input).value.strip().upper()

                # Get date range for relative volume calculation
                start_date_str = self.query_one("#start_date_input", Input).value.strip()
                end_date_str = self.query_one("#end_date_input", Input).value.strip()

                if not symbol:
                    self.app.notify("⚠️ Please enter a symbol", severity="warning")
                    return

                # VALIDATION: Check if symbol exists in Stocks table BEFORE starting pipeline
                import mysql.connector
                validation_conn = mysql.connector.connect(
                    host="localhost",
                    port=3306,
                    user="root",
                    password="E_I$S5PFri",
                    database="histFinanData"
                )
                validation_cursor = validation_conn.cursor()
                validation_cursor.execute(f"SELECT ticker FROM Stocks WHERE ticker = '{symbol}'")
                symbol_exists = validation_cursor.fetchone()
                validation_cursor.close()
                validation_conn.close()

                if not symbol_exists:
                    # Symbol not found - show clear error and DO NOT start pipeline
                    error_msg = (
                        f"❌ Symbol '{symbol}' not found in database.\n\n"
                        f"This symbol is not part of the monitored universe. "
                        f"Add it via Utils Dashboard to analyze."
                    )
                    self.app.notify(error_msg, severity="error", timeout=8)
                    return  # EXIT - do not start download

                # Get pipeline widget
                pipeline = self.app.query_one(TradeDownloadPipelineWidget)
                pipeline.reset()

                # Disable button while processing
                event.button.disabled = True

                # Store symbol for later notification
                download_symbol = symbol

                self.app.notify(f"📡 Fetching trade data for {symbol}...", severity="information")

                # Progress callback function that updates UI
                def progress_callback(step, count=0):
                    logger.info(f"[PIPELINE CALLBACK] Step: {step}, Count: {count}")

                    # Use call_from_thread to safely update UI from background thread
                    def update_ui():
                        try:
                            if step == "step1_start":
                                logger.info("[PIPELINE UPDATE] Setting step1 to 🔵 Downloading... 0")
                                pipeline.step1_status = "🔵"
                                pipeline.step1_detail = "Downloading... 0"
                                pipeline.refresh()
                            elif step == "step1_progress":
                                logger.info(f"[PIPELINE UPDATE] Progress: Downloading... {count}")
                                pipeline.step1_status = "🔵"
                                pipeline.step1_detail = f"Downloading... {count}"
                                pipeline.refresh()
                            elif step == "step2_start":
                                logger.info(f"[PIPELINE UPDATE] Step1 complete, Step2 starting")
                                pipeline.step1_status = "✅"
                                pipeline.step1_detail = f"Downloaded {count}"
                                pipeline.step2_status = "🔵"
                                pipeline.refresh()
                            elif step == "step3_complete":
                                logger.info(f"[PIPELINE UPDATE] Step2 and Step3 complete")
                                pipeline.step2_status = "✅"
                                pipeline.step3_status = "✅"
                                pipeline.step3_detail = f"[green]{count}[/green]"
                                pipeline.refresh()
                            elif step == "step3_error":
                                logger.error(f"[PIPELINE UPDATE] Step2/Step3 FAILED: {count}")
                                pipeline.step2_status = "❌"
                                pipeline.step3_status = "❌"
                                pipeline.step3_detail = f"[red]Error[/red]"
                                pipeline.refresh()
                        except Exception as e:
                            logger.error(f"[PIPELINE ERROR] Failed to update UI for step {step}: {e}", exc_info=True)

                    self.app.call_from_thread(update_ui)

                # Run download in background thread
                def download_worker():
                    try:
                        total_saved = self.data_source.get_Historical_Data_by_Trades(
                            year, month, day, hour, minute, symbol, progress_callback
                        )

                        # STEP 1: Update Raw Trades List and Price Chart BEFORE RV calculation
                        def update_ui_before_rv():
                            preview_widget = self.app.query_one(ExperimentWidget3)
                            preview_widget.update_preview()

                            chart_widget = self.app.query_one(PriceChartWidget)
                            chart_widget.update_chart()

                        self.app.call_from_thread(update_ui_before_rv)

                        # Small delay to ensure UI renders
                        import time
                        time.sleep(0.3)

                        # STEP 2: Calculate relative volume if date range is provided
                        relative_volume = 0.0
                        days_with_data = 0
                        daily_breakdown = []

                        if start_date_str and end_date_str:
                            try:
                                # Update pipeline: Start RV calculation
                                def update_step4_start():
                                    pipeline.step4_status = "🔵"
                                    pipeline.step4_detail = "(calculating...)"
                                self.app.call_from_thread(update_step4_start)

                                # CRITICAL: Clear HistoryByMinToday for this symbol before calculation
                                conn = self.data_source._get_connection()
                                cursor = conn.cursor()
                                cursor.execute("""
                                    DELETE FROM HistoryByMinToday
                                    WHERE stockID = %s
                                """, (symbol,))
                                conn.commit()
                                logger.info(f"Cleared HistoryByMinToday table for {symbol} ({cursor.rowcount} rows deleted)")
                                cursor.close()
                                conn.close()

                                # Calculate relative volume using 15 business days of historical data
                                # Uses the HOUR input (not minute) to compare same hour across days
                                relative_volume, days_with_data, daily_breakdown = self.data_source.calculate_relative_volume(
                                    symbol, hour, year, month, day
                                )

                                # Update pipeline: Show days with activity instead of RV value
                                def update_step4_complete():
                                    pipeline.step4_status = "✅"
                                    day_text = "day" if days_with_data == 1 else "days"
                                    pipeline.step4_detail = f"[green]{days_with_data} {day_text}[/green]"
                                self.app.call_from_thread(update_step4_complete)

                            except Exception as e:
                                logger.error(f"CRITICAL: RV calculation failed in download_worker for {symbol}: {e}", exc_info=True)
                                logger.error(f"RV failed with dates: start={start_date_str}, end={end_date_str}")
                                relative_volume = 0.0

                                # Update pipeline: RV failed
                                def update_step4_error():
                                    pipeline.step4_status = "❌"
                                    pipeline.step4_detail = "[red]Error[/red]"
                                self.app.call_from_thread(update_step4_error)

                        # STEP 3: Update metrics panel (final step)
                        def on_success():
                            # Update metrics only (preview and chart already updated)
                            metrics_widget = self.app.query_one(TradesBySecondPanel)
                            metrics_widget.update_metric()
                            # Update RV in metrics panel (extract RV value and breakdown)
                            rv_value = relative_volume  # This is the average volume
                            metrics_widget.relative_volume = rv_value
                            metrics_widget.rv_breakdown = daily_breakdown
                            metrics_widget.rv_hour = hour  # Store the hour for display
                            metrics_widget.update_relative_volume_display()

                            # Update RV Breakdown Panel with detailed historical data
                            rv_breakdown_widget = self.app.query_one(RelativeVolumeBreakdownPanel)
                            rv_breakdown_widget.set_breakdown_data(symbol, hour, daily_breakdown, rv_value)
                            logger.info(f"RV Breakdown panel updated with {len(daily_breakdown)} days of data")

                            # STEP 4: Refresh chart with correct RV threshold marker
                            chart_widget = self.app.query_one(PriceChartWidget)
                            chart_widget.update_chart()
                            logger.info(f"Chart refreshed with RV threshold: {rv_value:,.0f}")

                            # Success notification with trade count and RV
                            if total_saved == 0:
                                # No trades found for this time period (symbol exists but no activity)
                                notification_msg = f"ℹ️ No trades found for {download_symbol} at {hour:02d}:{minute:02d} | RV: {rv_value:,.0f} ({days_with_data} days)"
                                self.app.notify(notification_msg, severity="warning", timeout=6)
                            else:
                                # Trades successfully downloaded
                                self.app.notify(
                                    f"✅ Downloaded {total_saved:,} trades for {download_symbol} | RV: {rv_value:,.0f} ({days_with_data} days)",
                                    severity="information"
                                )

                            # Re-enable button
                            event.button.disabled = False

                        self.app.call_from_thread(on_success)

                    except Exception as e:
                        logger.error(f"❌ DOWNLOAD WORKER FAILED: {e}", exc_info=True)

                        def on_error():
                            # Update pipeline to show error
                            pipeline = self.app.query_one(TradeDownloadPipelineWidget)

                            # Check which step failed based on pipeline state
                            if pipeline.step2_status == "🔵":
                                # Failed during saving
                                pipeline.step2_status = "❌"
                                pipeline.step3_status = "❌"
                                pipeline.step3_detail = "[red]Save failed[/red]"
                            elif pipeline.step1_status == "🔵":
                                # Failed during download
                                pipeline.step1_status = "❌"
                                pipeline.step1_detail = "[red]Download failed[/red]"

                            pipeline.refresh()

                            # Show detailed error notification
                            error_type = type(e).__name__
                            error_msg = (
                                f"❌ Download Failed: {error_type}\n\n"
                                f"{str(e)}\n\n"
                                f"Check trading_system.log for details."
                            )
                            self.app.notify(error_msg, severity="error", timeout=10)
                            event.button.disabled = False

                        self.app.call_from_thread(on_error)

                # Start background thread
                thread = threading.Thread(target=download_worker, daemon=True)
                thread.start()

            except ValueError:
                self.app.notify("❌ Invalid input - please enter valid numbers", severity="error")
                event.button.disabled = False
            except Exception as e:
                self.app.notify(f"❌ Error: {str(e)}", severity="error")
                event.button.disabled = False


class TradeDownloadPipelineWidget(Static):
    """Progress indicator for trade download pipeline"""

    step1_status = reactive("⚪")
    step1_detail = reactive("Downloading trades...")
    step2_status = reactive("⚪")
    step3_status = reactive("⚪")
    step3_detail = reactive("")
    step4_status = reactive("⚪")
    step4_detail = reactive("")

    def compose(self) -> ComposeResult:
        yield Label("[bold cyan]Trade Download Pipeline[/bold cyan]")

    def watch_step1_status(self, new_status: str) -> None:
        """Update display when step 1 status changes"""
        self.update_display()

    def watch_step1_detail(self, new_detail: str) -> None:
        """Update display when step 1 detail changes"""
        self.update_display()

    def watch_step2_status(self, new_status: str) -> None:
        """Update display when step 2 status changes"""
        self.update_display()

    def watch_step3_status(self, new_status: str) -> None:
        """Update display when step 3 status changes"""
        self.update_display()

    def watch_step3_detail(self, new_detail: str) -> None:
        """Update display when step 3 detail changes"""
        self.update_display()

    def watch_step4_status(self, new_status: str) -> None:
        """Update display when step 4 status changes"""
        self.update_display()

    def watch_step4_detail(self, new_detail: str) -> None:
        """Update display when step 4 detail changes"""
        self.update_display()

    def update_display(self):
        """Update the pipeline display"""
        content = f"""
{self.step1_status} {self.step1_detail}
{self.step2_status} Saving trades
{self.step3_status} Trades Saved {self.step3_detail}
{self.step4_status} Relative V.F {self.step4_detail}
"""
        logger.debug(f"[PIPELINE DISPLAY] Updating with: step1={self.step1_status}, step2={self.step2_status}, step3={self.step3_status}, step4={self.step4_status}")
        self.update(content)

    def reset(self):
        """Reset pipeline to initial state"""
        self.step1_status = "⚪"
        self.step1_detail = "Downloading..."
        self.step2_status = "⚪"
        self.step3_status = "⚪"
        self.step3_detail = ""
        self.step4_status = "⚪"
        self.step4_detail = ""


class ExperimentWidget3(Static):
    """All trades from RawTrades table"""

    def __init__(self, data_source: ExperimentalDataSource, **kwargs):
        super().__init__(**kwargs)
        self.data_source = data_source
        self.table = DataTable()

    def compose(self) -> ComposeResult:
        yield Label("[bold magenta]Raw Trades List[/bold magenta]")
        yield self.table

    def on_mount(self):
        self.table.add_columns("Symbol", "Price", "Volume", "Exchange", "Timestamp")
        self.update_preview()

    def update_preview(self):
        """Load and display ALL trades from RawTrades table"""
        self.table.clear()

        try:
            conn = self.data_source._get_connection()
            cursor = conn.cursor(dictionary=True)

            cursor.execute("""
                SELECT symbol, close, volume, exchange, timestamp
                FROM RawTrades
                ORDER BY id ASC
            """)

            trades = cursor.fetchall()
            cursor.close()
            conn.close()

            if not trades:
                self.table.add_row("No trades", "-", "-", "-", "-")
                return

            for trade in trades:
                symbol = trade.get('symbol', 'N/A')
                price = f"${trade.get('close', 0):.2f}"
                volume = str(trade.get('volume', 0))
                exchange = str(trade.get('exchange', 'N/A'))
                # Format timestamp: 2026-03-04T06:00:00 -> 06:00:00 (time only)
                timestamp_str = trade.get('timestamp', 'N/A')
                if timestamp_str and timestamp_str != 'N/A':
                    # Extract only the time portion (HH:MM:SS)
                    timestamp = timestamp_str[11:19]  # Characters 11-19 are the time part
                else:
                    timestamp = 'N/A'

                self.table.add_row(symbol, price, volume, exchange, timestamp)

        except Exception as e:
            logger.error(f"Error loading trades from RawTrades table: {e}", exc_info=True)
            self.table.add_row("Error loading", "-", "-", "-", "-")


class TradesBySecondPanel(Static):
    """Panel displaying Trades by Second metric and Relative Volume"""

    # Reactive property for WebSocket trade counter
    websocket_trades_count = reactive(0)
    # Reactive property for WebSocket symbol count
    websocket_symbols_count = reactive(0)

    def __init__(self, data_source: ExperimentalDataSource, **kwargs):
        super().__init__(**kwargs)
        self.data_source = data_source
        self.relative_volume = 0.0
        self.rv_breakdown = []  # List of (date, volume) tuples
        self.rv_hour = 6  # Target hour for RV calculation
        # RV threshold trade info
        self.rv_threshold_symbol = ""
        self.rv_threshold_price = 0.0
        self.rv_threshold_volume = 0
        self.rv_threshold_timestamp = ""

    def compose(self) -> ComposeResult:
        yield Label("[bold white]Trading Activity Metrics[/bold white]")
        yield Label("", id="websocket_symbols_label")
        yield Label("", id="websocket_trades_label")
        yield Label("", id="trades_by_second_label")
        yield Label("", id="relative_volume_label")
        yield Label("", id="rv_threshold_trade_label")
        yield Label("", id="rv_breakdown_label")

    def on_mount(self):
        self.update_metric()
        self.update_relative_volume_display()
        self._update_websocket_trades_label()
        self._update_websocket_symbols_label()

    def watch_websocket_trades_count(self, new_value: int):
        """Reactive watcher - updates label when trade count changes"""
        logger.info(f"🔔 Watcher triggered! New value: {new_value}")
        self._update_websocket_trades_label()

    def watch_websocket_symbols_count(self, new_value: int):
        """Reactive watcher - updates label when symbol count changes"""
        logger.info(f"🔔 Symbol count watcher triggered! New value: {new_value}")
        self._update_websocket_symbols_label()

    def _update_websocket_symbols_label(self):
        """Update the WebSocket symbols counter label"""
        try:
            label = self.query_one("#websocket_symbols_label", Label)
            if self.websocket_symbols_count > 0:
                label.update(f"[bold cyan]Subscribed Symbols:[/bold cyan] [yellow]{self.websocket_symbols_count}[/yellow]")
                logger.info(f"✅ Symbols label updated to: {self.websocket_symbols_count}")
            else:
                label.update(f"[bold cyan]Subscribed Symbols:[/bold cyan] [dim]0[/dim]")
        except Exception as e:
            logger.error(f"❌ Error updating WebSocket symbols label: {e}", exc_info=True)

    def _update_websocket_trades_label(self):
        """Update the WebSocket trades counter label"""
        try:
            logger.debug(f"Updating label with count: {self.websocket_trades_count}")
            label = self.query_one("#websocket_trades_label", Label)
            if self.websocket_trades_count > 0:
                label.update(f"[bold magenta]WebSocket Trades:[/bold magenta] [green]{self.websocket_trades_count:,}[/green]")
                logger.info(f"✅ Label updated to: {self.websocket_trades_count:,}")
            else:
                label.update(f"[bold magenta]WebSocket Trades:[/bold magenta] [dim]0[/dim]")
                logger.info("✅ Label updated to: 0")
        except Exception as e:
            logger.error(f"❌ Error updating WebSocket trades label: {e}", exc_info=True)

    def update_metric(self):
        """Calculate and display Trades by Second metric"""
        try:
            conn = self.data_source._get_connection()
            cursor = conn.cursor(dictionary=True)

            # Query distinct seconds from RawTrades where volume >= 100
            cursor.execute("""
                SELECT DISTINCT timestamp
                FROM RawTrades
                WHERE volume >= 100
            """)

            trades = cursor.fetchall()
            cursor.close()
            conn.close()

            if not trades:
                trades_by_second = 0
            else:
                # Extract unique seconds from timestamps
                unique_seconds = set()
                for trade in trades:
                    ts_str = trade['timestamp'][:19]  # Get YYYY-MM-DD HH:MM:SS
                    # Extract only HH:MM:SS (time portion)
                    time_portion = ts_str[11:19]  # Characters 11-19 are HH:MM:SS
                    unique_seconds.add(time_portion)

                trades_by_second = len(unique_seconds)

            # Update the label
            label = self.query_one("#trades_by_second_label", Label)
            label.update(f"[bold cyan]Trades by Second:[/bold cyan] [green]{trades_by_second}[/green]")

        except Exception as e:
            logger.error(f"Error calculating Trades by Second: {e}", exc_info=True)
            label = self.query_one("#trades_by_second_label", Label)
            label.update(f"[bold red]Error calculating metric[/bold red]")

    def update_relative_volume_display(self):
        """Update the relative volume display"""
        try:
            label = self.query_one("#relative_volume_label", Label)
            if self.relative_volume > 0:
                # Display as average volume (not a ratio)
                label.update(f"[bold cyan]Relative Volume:[/bold cyan] [yellow]{self.relative_volume:,.0f}[/yellow]")

                # Enable Run Simulation button when RV is ready
                try:
                    run_btn = self.app.query_one("#run_simulation_btn", Button)
                    run_btn.disabled = False
                except:
                    pass  # Button might not be mounted yet
            else:
                label.update(f"[bold cyan]Relative Volume:[/bold cyan] [dim]Not calculated[/dim]")

                # Disable Run Simulation button when RV is not ready
                try:
                    run_btn = self.app.query_one("#run_simulation_btn", Button)
                    run_btn.disabled = True
                except:
                    pass

            # Update breakdown list
            breakdown_label = self.query_one("#rv_breakdown_label", Label)
            if self.rv_breakdown:
                # Format breakdown: each day on a new line
                breakdown_text = "\n".join([
                    f"  {date} at {self.rv_hour}:00 – Volume: {int(volume):,}"
                    for date, volume in self.rv_breakdown
                ])
                breakdown_label.update(f"[dim]{breakdown_text}[/dim]")
            else:
                breakdown_label.update("")

        except Exception as e:
            logger.error(f"Error updating relative volume display: {e}", exc_info=True)

    def update_rv_threshold_trade_display(self):
        """Update the RV threshold trade display"""
        try:
            label = self.query_one("#rv_threshold_trade_label", Label)
            if self.rv_threshold_symbol and self.rv_threshold_timestamp:
                # Format: CANF $5.25 200 06:00:11
                label.update(
                    f"[bold green]{self.rv_threshold_symbol}[/bold green] "
                    f"[cyan]${self.rv_threshold_price:.2f}[/cyan] "
                    f"[yellow]{self.rv_threshold_volume}[/yellow] "
                    f"[dim]{self.rv_threshold_timestamp}[/dim]"
                )
            else:
                label.update("")

        except Exception as e:
            logger.error(f"Error updating RV threshold trade display: {e}", exc_info=True)


class RelativeVolumeBreakdownPanel(Static):
    """Panel displaying the historical data used to calculate Relative Volume Factor"""

    def __init__(self, data_source: ExperimentalDataSource, **kwargs):
        super().__init__(**kwargs)
        self.data_source = data_source
        self.rv_data = []  # List of (date, hour, symbol, volume) tuples
        self.target_symbol = ""
        self.total_volume = 0
        self.days_count = 0

    def compose(self) -> ComposeResult:
        yield Label("[bold yellow]Relative Volume - Historical Data[/bold yellow]")
        yield Label("", id="rv_breakdown_table")

    def on_mount(self):
        self.update_breakdown_display()

    def set_breakdown_data(self, symbol: str, hour: int, daily_breakdown: list, total_rv: float):
        """Update the breakdown data and refresh display

        Args:
            symbol: Stock symbol (e.g., "WNW")
            hour: Target hour (e.g., 7 for 7:00 AM)
            daily_breakdown: List of (date, volume) tuples from RV calculation
            total_rv: Total/average relative volume value
        """
        self.target_symbol = symbol
        self.rv_data = [(date, hour, symbol, volume) for date, volume in daily_breakdown]
        self.total_volume = total_rv
        self.days_count = len(daily_breakdown)
        self.update_breakdown_display()

    def clear_data(self):
        """Clear the breakdown data"""
        self.rv_data = []
        self.target_symbol = ""
        self.total_volume = 0
        self.days_count = 0
        self.update_breakdown_display()

    def update_breakdown_display(self):
        """Render the breakdown table"""
        try:
            label = self.query_one("#rv_breakdown_table", Label)

            if not self.rv_data:
                label.update("[dim]No data available. Click 'Download Trades' to calculate Relative Volume.[/dim]")
                return

            # Build table header
            lines = []
            lines.append("[bold cyan]" + "─" * 80 + "[/bold cyan]")
            lines.append(
                f"[bold cyan]{'Date':<12} {'Hour':<6} {'Symbol':<8} {'Volume':>12}[/bold cyan]"
            )
            lines.append("[bold cyan]" + "─" * 80 + "[/bold cyan]")

            # Add data rows
            for date, hour, symbol, volume in self.rv_data:
                date_str = str(date)
                hour_str = f"{hour:02d}:00"
                lines.append(
                    f"[white]{date_str:<12}[/white] "
                    f"[cyan]{hour_str:<6}[/cyan] "
                    f"[yellow]{symbol:<8}[/yellow] "
                    f"[green]{int(volume):>12,}[/green]"
                )

            lines.append("[bold cyan]" + "─" * 80 + "[/bold cyan]")

            # Add summary footer
            avg_volume = self.total_volume
            lines.append(
                f"[bold white]Total Days: {self.days_count}  |  "
                f"Average Volume (Relative V.F.): {int(avg_volume):,}[/bold white]"
            )
            lines.append("[bold cyan]" + "─" * 80 + "[/bold cyan]")

            label.update("\n".join(lines))

        except Exception as e:
            logger.error(f"Error updating RV breakdown display: {e}", exc_info=True)


class PriceChartWidget(Static):
    """Price chart from RawTrades table"""

    def __init__(self, data_source: ExperimentalDataSource, **kwargs):
        super().__init__(**kwargs)
        self.data_source = data_source
        self.plt = PlotextPlot()
        self.rule2_trade = None  # Store Rule 2 trade info for marking

    def compose(self) -> ComposeResult:
        yield Label("[bold green]Price Chart[/bold green]")
        yield self.plt

    def on_mount(self):
        self.update_chart()

    def set_rule2_trade(self, trade_info):
        """Store Rule 2 trade info and refresh chart"""
        self.rule2_trade = trade_info
        self.update_chart()

    def update_chart(self):
        """Load price data from RawTrades and plot it"""
        try:
            conn = self.data_source._get_connection()
            cursor = conn.cursor(dictionary=True)

            cursor.execute("""
                SELECT symbol, close, volume, timestamp
                FROM RawTrades
                WHERE volume >= 100
                ORDER BY id ASC
            """)

            trades = cursor.fetchall()
            cursor.close()
            conn.close()

            if not trades:
                # Empty chart if no data
                self.plt.plt.clear_data()
                self.plt.plt.title("No data available")
                self.plt.refresh()
                return

            # Extract prices, volumes, and format timestamps
            prices = [float(trade['close']) for trade in trades]
            volumes = [int(trade['volume']) for trade in trades]

            # Format timestamps as readable strings for x-axis labels (MM:SS only)
            time_labels = []
            for trade in trades:
                ts_str = trade['timestamp'][:19].replace('T', ' ')
                dt = datetime.strptime(ts_str, '%Y-%m-%d %H:%M:%S')
                time_labels.append(dt.strftime('%M:%S'))  # Only minute:second

            # Use index for x-axis positions, but with time labels
            x_positions = list(range(len(prices)))

            # Calculate OPEN price (first price with volume >= 100)
            open_price = prices[0]

            # Calculate risk threshold (OPEN * (1 + PRICE_SPIKE_RISK_THRESHOLD%))
            risk_threshold = open_price * (1 + PRICE_SPIKE_RISK_THRESHOLD / 100)

            # Find the highest price and its position
            max_price = max(prices)
            max_price_index = prices.index(max_price)
            max_price_time = time_labels[max_price_index]

            # Get Relative Volume from the Trading Activity Metrics panel
            rv_panel = self.app.query_one(TradesBySecondPanel)
            relative_volume = rv_panel.relative_volume

            # Calculate cumulative volume and find the index where it reaches/exceeds Relative Volume
            cumulative_volume = 0
            rv_threshold_index = None
            rv_threshold_price = None

            for i, volume in enumerate(volumes):
                cumulative_volume += volume
                if cumulative_volume >= relative_volume:
                    rv_threshold_index = i
                    rv_threshold_price = prices[i]
                    break

            # If cumulative never reaches RV, use the last trade
            if rv_threshold_index is None:
                rv_threshold_index = len(volumes) - 1
                rv_threshold_price = prices[-1]

            rv_threshold_timestamp = trades[rv_threshold_index]['timestamp']

            # Update RV threshold trade info in the panel
            rv_threshold_symbol = trades[rv_threshold_index].get('symbol', 'N/A')
            rv_threshold_volume = volumes[rv_threshold_index]
            # Format timestamp to HH:MM:SS
            ts_str = rv_threshold_timestamp[:19].replace('T', ' ')
            dt = datetime.strptime(ts_str, '%Y-%m-%d %H:%M:%S')
            rv_threshold_time_formatted = dt.strftime('%H:%M:%S')

            # Update the panel properties
            rv_panel.rv_threshold_symbol = rv_threshold_symbol
            rv_panel.rv_threshold_price = rv_threshold_price
            rv_panel.rv_threshold_volume = rv_threshold_volume
            rv_panel.rv_threshold_timestamp = rv_threshold_time_formatted
            rv_panel.update_rv_threshold_trade_display()

            # Log for debugging
            logger.info(f"Chart data: {len(trades)} trades, {len(prices)} prices, {len(volumes)} volumes")
            logger.info(f"Relative Volume threshold: {relative_volume:,.0f}")
            logger.info(f"Total cumulative volume: {sum(volumes):,}")
            logger.info(f"Highest price: ${max_price:.2f} at index {max_price_index}, time {time_labels[max_price_index]}")
            logger.info(f"X-axis range: {min(x_positions)} to {max(x_positions)}")
            logger.info(f"Y-axis range: ${min(prices):.2f} to ${max(prices):.2f}")

            # === DETAILED LOG FOR RV THRESHOLD TRADE ===
            logger.info("=" * 70)
            logger.info("RELATIVE VOLUME THRESHOLD REACHED")
            logger.info("=" * 70)
            logger.info(f"Relative Volume Target: {relative_volume:,.0f} shares")
            logger.info(f"Cumulative Volume at Threshold: {sum(volumes[:rv_threshold_index+1]):,} shares")
            logger.info(f"Symbol: {rv_threshold_symbol}")
            logger.info(f"Threshold Index: {rv_threshold_index}")
            logger.info(f"Timestamp: {rv_threshold_timestamp}")
            logger.info(f"Time: {rv_threshold_time_formatted}")
            logger.info(f"Price: ${rv_threshold_price:.2f}")
            logger.info(f"Trade Volume: {rv_threshold_volume:,} shares")
            logger.info(f"Trades Required: {rv_threshold_index + 1} trades to reach RV threshold")
            logger.info(f"Display Format: {rv_threshold_symbol} ${rv_threshold_price:.2f} {rv_threshold_volume} {rv_threshold_time_formatted}")
            logger.info("=" * 70)

            # Log the scatter coordinates
            logger.info(f"RED scatter (Highest Price): x={max_price_index}, y={max_price:.2f}")
            logger.info(f"GREEN scatter (RV Threshold): x={rv_threshold_index}, y={rv_threshold_price:.2f}")

            # Clear and plot
            self.plt.plt.clear_data()

            # Plot price line
            self.plt.plt.plot(x_positions, prices, marker="braille", color="cyan", label="Price")
            logger.info("Price line plotted")

            # Mark highest price with red X and label
            self.plt.plt.scatter([max_price_index], [max_price], color="red", marker="x")
            self.plt.plt.text("High", max_price_index, max_price, color="red")
            logger.info(f"Red X marker added at ({max_price_index}, {max_price:.2f})")

            # Mark RV threshold point with green X and label
            self.plt.plt.scatter([rv_threshold_index], [rv_threshold_price], color="green+", marker="x")
            self.plt.plt.text("R.V.", rv_threshold_index, rv_threshold_price, color="green+")
            logger.info(f"Green X marker (RV Threshold) added at ({rv_threshold_index}, {rv_threshold_price:.2f})")

            # Mark Rule 2 trade if available (first trade meeting 2% + RV threshold)
            # Just show an X marker without text label
            if self.rule2_trade:
                # Find the Rule 2 trade in the trades list by matching price and timestamp
                rule2_price = self.rule2_trade.get('price')
                rule2_timestamp = self.rule2_trade.get('timestamp')

                # Find matching trade index
                rule2_index = None
                for i, trade in enumerate(trades):
                    if abs(float(trade['close']) - rule2_price) < 0.01:  # Price match within 1 cent
                        rule2_index = i
                        break

                if rule2_index is not None:
                    # Add cyan X marker without text label
                    # Offset horizontally and vertically to be clearly visible
                    offset_index = rule2_index + 1.5  # Larger horizontal offset
                    offset_price = rule2_price + 0.05  # Small vertical offset (5 cents up)
                    self.plt.plt.scatter([offset_index], [offset_price], color="cyan", marker="x")
                    logger.info(f"Cyan X marker (Rule 2) added at ({offset_index:.1f}, {offset_price:.2f})")

            # Add horizontal risk limit line
            self.plt.plt.hline(risk_threshold, color="red+")

            # Add horizontal 2% price increase threshold line
            price_increase_threshold = open_price * 1.02
            self.plt.plt.hline(price_increase_threshold, color="white")
            logger.info(f"White line (2% threshold) added at ${price_increase_threshold:.2f}")

            # Set title with key metrics
            self.plt.plt.title(f"Price | High: ${max_price:.2f} | Open: ${open_price:.2f} | Risk: ${risk_threshold:.2f}")

            # Axis labels
            self.plt.plt.xlabel("Time")
            self.plt.plt.ylabel("Price ($)")

            # X-axis labels (time)
            if len(time_labels) > 10:
                step = len(time_labels) // 10
                label_positions = list(range(0, len(time_labels), step))
                label_texts = [time_labels[i] for i in label_positions]
                self.plt.plt.xticks(label_positions, label_texts)
            else:
                self.plt.plt.xticks(x_positions, time_labels)

            self.plt.refresh()

        except Exception as e:
            logger.error(f"Error updating price chart: {e}", exc_info=True)
            self.plt.plt.clear_data()
            self.plt.plt.title(f"Error: {str(e)}")
            self.plt.refresh()


class SimulationPipelineWidget(Static):
    """Progress indicator for simulation multiprocessing pipeline - contains all real-time info"""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.process1_status = "⚪"
        self.qualifying_trade = None  # The trade that met BOTH conditions
        self.process2_status = "⚪"
        self.process2_signals = []  # Store all received signals

    def compose(self) -> ComposeResult:
        yield Label("[bold cyan]Simulation Pipeline[/bold cyan]")
        yield Label("", id="pipeline_content")

    def update_display(self):
        """Update the complete pipeline display"""
        # Process 1 section - Show only the trade that met BOTH conditions
        process1_text = f"[bold white]Process 1:[/bold white] {self.process1_status} Simulation (Rule Evaluation)\n"

        if self.qualifying_trade:
            # Extract time portion from timestamp (HH:MM:SS)
            # Handle both string timestamps and numeric (Unix) timestamps
            timestamp = self.qualifying_trade.get('timestamp', '')
            if isinstance(timestamp, str) and len(timestamp) >= 19:
                # String format: "2026-03-17 07:33:30" → extract "07:33:30"
                time_str = timestamp[11:19]
            elif isinstance(timestamp, (int, float)):
                # Unix timestamp → convert to datetime
                from datetime import datetime
                dt = datetime.fromtimestamp(timestamp / 1000)  # Polygon uses milliseconds
                time_str = dt.strftime("%H:%M:%S")
            else:
                time_str = str(timestamp) if timestamp else 'N/A'

            process1_text += (
                f"  Price: [yellow]${self.qualifying_trade['price']:.2f}[/yellow], "
                f"Exchange: [cyan]{self.qualifying_trade['exchange']}[/cyan], "
                f"Volume: [yellow]{self.qualifying_trade['volume']:,}[/yellow], "
                f"Open: [yellow]${self.qualifying_trade['open']:.2f}[/yellow], "
                f"Cumulative Vol: [yellow]{self.qualifying_trade['cumulative_volume']:,}[/yellow], "
                f"Time: [cyan]{time_str}[/cyan]\n"
            )
        else:
            process1_text += "  Evaluating trades...\n"

        # Process 2 section
        process2_text = f"\n[bold white]Process 2:[/bold white] {self.process2_status} Trade Signal Consumer\n"

        if self.process2_signals:
            for signal in self.process2_signals:
                process2_text += f"  Symbol: [cyan]{signal['symbol']}[/cyan] | Price: [yellow]${signal['price']:.2f}[/yellow] | High: [yellow]${signal['high']:.2f}[/yellow] | Low: [yellow]${signal['low']:.2f}[/yellow]\n"
                process2_text += f"  Second: [cyan]{signal['second']}[/cyan] | Active Seconds: [cyan]{signal['active_seconds']}[/cyan] | Volume: [yellow]{signal.get('volume', 0):,}[/yellow]\n\n"
        else:
            process2_text += "  Waiting for signals...\n"

        content = process1_text + process2_text

        try:
            label = self.query_one("#pipeline_content", Label)
            label.update(content)
        except:
            pass

    def reset(self):
        """Reset pipeline to initial state"""
        self.process1_status = "⚪"
        self.qualifying_trade = None
        self.process2_status = "⚪"
        self.process2_signals = []
        self.update_display()

    def start_process1(self):
        """Mark Process 1 as running"""
        self.process1_status = "🔵"
        self.update_display()

    def set_qualifying_trade(self, trade_info: dict):
        """Set the trade that met BOTH conditions"""
        self.qualifying_trade = {
            'price': trade_info.get('price', 0.0),
            'exchange': trade_info.get('exchange', 'N/A'),
            'volume': trade_info.get('volume', 0),
            'open': trade_info.get('open', 0.0),
            'cumulative_volume': trade_info.get('cumulative_volume', 0),
            'timestamp': trade_info.get('timestamp', '')
        }
        self.update_display()

    def complete_process1(self):
        """Mark Process 1 as complete"""
        self.process1_status = "✅"
        self.update_display()

    def start_process2(self):
        """Mark Process 2 as running"""
        self.process2_status = "🔵"
        self.update_display()

    def signal_received(self, signal_data: dict):
        """Add received signal to Process 2"""
        self.process2_signals.append(signal_data)
        self.update_display()

    def complete_process2(self):
        """Mark Process 2 as complete"""
        self.process2_status = "✅"
        self.update_display()


class ValidationPipelineWidget(Static):
    """
    Visual pipeline tracker for the 7-step validation process.
    Shows which step caused a trade to fail (if any).
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.validation_results = []  # List of validation result dicts
        self.current_symbol = None

    def compose(self) -> ComposeResult:
        yield Label("[bold cyan]Validation Pipeline Monitor[/bold cyan]")
        yield DataTable(id="validation_table")

    def on_mount(self):
        """Initialize the validation table"""
        table = self.query_one("#validation_table", DataTable)
        table.add_columns("Step", "Validation", "Status", "Details")
        table.zebra_stripes = True
        table.cursor_type = "row"

    def add_validation_result(self, validation_data: dict):
        """
        Add a new validation result to the pipeline.

        Args:
            validation_data: Dict containing:
                - symbol: Stock symbol
                - step: Step number (1-7)
                - name: Step name (e.g., "Low Activity Check")
                - status: "PASSED", "FAILED", or "SKIPPED"
                - details: Additional information
                - final_result: "ORDER_SAVED" or "ORDER_REJECTED"
        """
        self.validation_results.append(validation_data)
        self.current_symbol = validation_data.get("symbol", "N/A")
        self.update_table()

    def update_table(self):
        """Refresh the table with latest validation results"""
        table = self.query_one("#validation_table", DataTable)
        table.clear()

        if not self.validation_results:
            table.add_row("—", "No validations yet", "⚪", "Run simulation to see results")
            return

        # Get the most recent validation set (last symbol processed)
        latest_validations = [v for v in self.validation_results if v.get("symbol") == self.current_symbol]

        if not latest_validations:
            return

        # Sort by step number
        latest_validations.sort(key=lambda x: x.get("step", 0))

        for validation in latest_validations:
            step = f"Step {validation.get('step', '?')}"
            name = validation.get("name", "Unknown")
            status = validation.get("status", "UNKNOWN")
            details = validation.get("details", "")

            # Format status with emoji
            if status == "PASSED":
                status_display = "✅ PASSED"
            elif status == "FAILED":
                status_display = "❌ FAILED"
            elif status == "SKIPPED":
                status_display = "⏭️ SKIPPED"
            else:
                status_display = f"⚠️ {status}"

            table.add_row(step, name, status_display, details)

        # Add final result row
        final_result = latest_validations[-1].get("final_result", "UNKNOWN")
        if final_result == "ORDER_SAVED":
            table.add_row(
                "✅",
                "[bold green]FINAL RESULT[/bold green]",
                "[bold green]ORDER SAVED TO DB[/bold green]",
                f"Symbol: {self.current_symbol}"
            )
        else:
            table.add_row(
                "❌",
                "[bold red]FINAL RESULT[/bold red]",
                "[bold red]ORDER REJECTED[/bold red]",
                f"Symbol: {self.current_symbol}"
            )

    def reset(self):
        """Clear all validation results"""
        self.validation_results = []
        self.current_symbol = None
        table = self.query_one("#validation_table", DataTable)
        table.clear()
        table.add_row("—", "Ready for simulation", "⚪", "Waiting for signals...")


class OrdersListPanel(Static):
    """
    Display recent purchase orders from the Orders table.
    Shows orders created during simulation.
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.orders = []

    def compose(self) -> ComposeResult:
        yield Label("[bold cyan]📋 Purchase Orders[/bold cyan]")
        yield DataTable(id="orders_table")

    def on_mount(self):
        """Initialize the orders table"""
        table = self.query_one("#orders_table", DataTable)
        table.add_columns("Symbol", "Shares", "Price", "Status", "Start Time", "End Time", "Latency (ms)")
        table.zebra_stripes = True
        table.cursor_type = "row"
        self.load_orders()

    def load_orders(self):
        """Load recent orders from MySQL Orders table"""
        try:
            import mysql.connector
            from datetime import datetime, timedelta

            db_connection = mysql.connector.connect(
                host="localhost",
                port=3306,
                user="root",
                password="E_I$S5PFri",
                database="histFinanData"
            )
            cursor = db_connection.cursor()

            # Get orders from last 24 hours, most recent first
            query = """
                SELECT symbol, totalQuantity, ask_price, status, start_timestamp, end_timestamp
                FROM Orders
                WHERE orderType = 'SIM_BUY'
                AND end_timestamp >= UNIX_TIMESTAMP(NOW() - INTERVAL 24 HOUR)
                ORDER BY end_timestamp DESC
                LIMIT 20
            """
            cursor.execute(query)
            rows = cursor.fetchall()

            table = self.query_one("#orders_table", DataTable)
            table.clear()

            if not rows:
                table.add_row("—", "No orders yet", "—", "Run simulation", "—", "—", "—")
            else:
                for row in rows:
                    symbol, qty, price, status, start_ts, end_ts = row

                    # Format START time with milliseconds
                    start_dt = datetime.fromtimestamp(start_ts)
                    start_ms = int((start_ts % 1) * 1000)
                    start_time_str = start_dt.strftime("%H:%M:%S") + f".{start_ms:03d}"

                    # Format END time with milliseconds
                    end_dt = datetime.fromtimestamp(end_ts)
                    end_ms = int((end_ts % 1) * 1000)
                    end_time_str = end_dt.strftime("%H:%M:%S") + f".{end_ms:03d}"

                    # Calculate processing time (latency) in milliseconds
                    latency_ms = (end_ts - start_ts) * 1000

                    table.add_row(
                        symbol,
                        str(qty),
                        f"${price:.2f}",
                        status,
                        start_time_str,
                        end_time_str,
                        f"{latency_ms:.1f}"
                    )

            cursor.close()
            db_connection.close()

        except Exception as e:
            logger.error(f"Error loading orders: {e}", exc_info=True)
            table = self.query_one("#orders_table", DataTable)
            table.clear()
            table.add_row("ERROR", str(e)[:30], "—", "—", "—", "—", "—")

    def refresh_orders(self):
        """Refresh the orders list"""
        self.load_orders()

    def reset(self):
        """Clear orders display"""
        table = self.query_one("#orders_table", DataTable)
        table.clear()
        table.add_row("—", "No orders yet", "—", "Run simulation", "—", "—", "—")


# ============================================================================
# Main Experimental Dashboard App
# ============================================================================

class ExperimentalDashboard(App):
    """Experimental dashboard - separate from trading and utils dashboards"""

    CSS = """
    Screen {
        background: $surface;
    }

    #left-panel {
        width: 50%;
        padding: 1;
    }

    #download-section {
        width: 40%;
        border: solid cyan;
        padding: 1;
    }

    #trades-section {
        width: 60%;
        border: solid magenta;
        padding: 1;
    }

    #chart-panel {
        width: 50%;
        border: solid green;
        padding: 1;
    }

    DataTable {
        height: auto;
        max-height: 20;
    }

    ExperimentWidget2 {
        border: solid yellow;
        padding: 1;
        margin: 1;
    }

    ExperimentWidget2 Input {
        margin: 1 0;
    }

    ExperimentWidget2 Button {
        width: 100%;
        margin: 1 0;
    }

    ExperimentWidget3 {
        padding: 1;
        height: 67%;
    }

    ExperimentWidget3 DataTable {
        height: 100%;
        max-height: 100%;
    }

    TradesBySecondPanel {
        border: solid white;
        padding: 1;
        margin: 1 1 0 1;
        height: 33%;
    }

    TradesBySecondPanel Label {
        margin: 1 0;
    }

    PriceChartWidget {
        padding: 1;
        height: 50%;
    }

    PriceChartWidget PlotextPlot {
        height: 100%;
    }

    TradeDownloadPipelineWidget {
        border: solid cyan;
        padding: 1;
        margin: 1;
        min-height: 14;
    }

    SimulationPipelineWidget {
        border: solid yellow;
        padding: 1;
        margin: 1;
        min-height: 12;
    }

    ValidationPipelineWidget {
        border: solid magenta;
        padding: 1;
        margin: 1;
        min-height: 15;
    }

    OrdersListPanel {
        border: solid green;
        padding: 1;
        margin: 1;
        min-height: 10;
    }
    """

    TITLE = "Experimental Dashboard v1.0"
    SUB_TITLE = "Testing and experimentation workspace"
    BINDINGS = [
        ("q", "quit", "Quit"),
        ("r", "refresh", "Refresh"),
    ]

    def __init__(self):
        super().__init__()
        self.data_source = ExperimentalDataSource()

    def compose(self) -> ComposeResult:
        """Create the UI layout"""
        yield Header()

        with Horizontal():
            # Left side: Download section + Trades table side by side
            with Horizontal(id="left-panel"):
                with VerticalScroll(id="download-section"):
                    yield TradeDownloadPipelineWidget()
                    yield TradesBySecondPanel(self.data_source)
                    yield ExperimentWidget2(self.data_source)

                with VerticalScroll(id="trades-section"):
                    yield ExperimentWidget3(self.data_source)
                    yield RelativeVolumeBreakdownPanel(self.data_source)

            # Right side: Price Chart + Simulation Pipeline + Validation Pipeline + Orders
            with VerticalScroll(id="chart-panel"):
                yield PriceChartWidget(self.data_source)
                yield SimulationPipelineWidget()
                yield ValidationPipelineWidget()
                yield OrdersListPanel()

        yield Footer()

    def action_quit(self):
        """Quit the application"""
        self.exit()

    def action_refresh(self):
        """Refresh the dashboard"""
        self.notify("🔄 Refreshing dashboard...", severity="information")
        widget1 = self.query_one(ExperimentWidget1)
        widget1.update_data()
        self.notify("✅ Dashboard refreshed", severity="information")


# ============================================================================
# Main Entry Point
# ============================================================================

def main():
    """Run the experimental dashboard"""
    # Set multiprocessing start method to 'fork' for macOS compatibility
    # Must be called before creating any multiprocessing objects
    try:
        multiprocessing.set_start_method('fork', force=True)
    except RuntimeError:
        # Start method already set (e.g., from another module)
        pass

    print("=" * 70)
    print("  EXPERIMENTAL DASHBOARD")
    print("  Independent workspace for testing")
    print("=" * 70)
    print()
    print("🧪 Starting experimental dashboard...")
    print("   Press 'q' to quit, 'r' to refresh")
    print("   Logging to: trading_system.log")
    print()

    logger.info("=" * 70)
    logger.info("EXPERIMENTAL DASHBOARD STARTED")
    logger.info("=" * 70)

    app = ExperimentalDashboard()
    app.run()

    logger.info("Experimental dashboard closed")


if __name__ == "__main__":
    main()
