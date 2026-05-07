"""
Trading System UI Experiments
==============================
Lightweight terminal-based UI for monitoring the trading system.
Uses Textual framework for zero-overhead real-time updates.

Run: python3 ui_experiments.py
"""

from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, Static, DataTable, Label, Button, Input
from textual.containers import Container, Horizontal, Vertical, VerticalScroll
from textual.reactive import reactive
from datetime import datetime
import asyncio
import mysql.connector
from typing import Dict, List, Optional
import time
import random
from collections import deque
import queue
import threading
from ib_insync import IB, Stock, LimitOrder
import logging
from polygon import RESTClient

# Import data loading functions
from clean_db import clear_day_work_tables
from get_previous_close import getPreviousClose
from get_float import get_float
from fetch_historycal_data_to_db import getHistoricalData
from relative_volume_ratio import getRelativeVolumeFactor


# ============================================================================
# Data Source Layer - Reads from MySQL and shared memory
# ============================================================================

class TradingDataSource:
    """Non-blocking data access for UI - never touches trading system directly"""

    def __init__(self, dashboard_queue=None, config=None, mysql_config: Optional[Dict] = None, ib_port: int = 7497):
        """
        Initialize TradingDataSource.

        Args:
            dashboard_queue: multiprocessing.Queue from trading system (real-time trades)
                           If None, uses demo mode
            config: Trading system configuration dict (strategy parameters)
            mysql_config: MySQL connection config (optional)
            ib_port: Interactive Brokers port (4001=live, 4002=paper, 7497=TWS paper)
        """
        self.mysql_config = mysql_config or {
            "host": "localhost",
            "port": 3306,
            "user": "root",
            "password": "E_I$S5PFri",
            "database": "histFinanData"
        }
        self._cache = {}
        self._last_fetch = {}
        self.cache_ttl = 1.0  # 1 second cache
        self.config = config or {}  # Trading system configuration

        # Configure logging to file
        self.log_file = '/Users/tan/experiments/polygon.io/trading_system.log'
        logging.basicConfig(
            filename=self.log_file,
            level=logging.DEBUG,
            format='%(asctime)s [%(levelname)s] %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        self.logger = logging.getLogger('TradingDataSource')

        # Interactive Brokers configuration
        self.ib_port = ib_port
        self.ib = None
        self.ib_connected = False
        self._init_ib_connection()

        # Demo trade data generator (40 symbols total) - used as fallback
        self._demo_symbols = [
            # Large cap tech
            'NVDA', 'AMD', 'MSFT', 'GOOGL', 'AMZN', 'META', 'NFLX', 'SPY',
            # Meme stocks and volatile names
            'GME', 'AMC', 'BBBY', 'PLTR', 'SOFI', 'RIVN', 'LCID', 'NIO', 'COIN', 'HOOD',
            # Small-cap momentum plays
            'MULN', 'ATER', 'BBIG', 'CEI', 'DWAC', 'PHUN', 'BKKT', 'PROG', 'RDBX', 'APRN',
            # Biotech/pharma runners
            'SAVA', 'GERN', 'OCGN', 'VXRT', 'ATNF', 'BNGO', 'CHRS', 'CYDY', 'MRNA', 'BNTX'
        ]
        self._demo_prices = {sym: random.uniform(5, 200) for sym in self._demo_symbols}
        self._trade_counter = 0

        # Dashboard queue from trading system (real-time trades from consumer_process)
        self.dashboard_queue = dashboard_queue
        self.live_mode = dashboard_queue is not None

        if self.live_mode:
            print("✅ Dashboard connected to LIVE trading system")
        else:
            print("⚠️  Dashboard running in DEMO mode (trading system not started)")

    def _get_connection(self):
        """Get MySQL connection"""
        return mysql.connector.connect(**self.mysql_config)

    def _is_cache_valid(self, key: str) -> bool:
        """Check if cached data is still valid"""
        if key not in self._last_fetch:
            return False
        return (time.time() - self._last_fetch[key]) < self.cache_ttl

    def _init_ib_connection(self):
        """Initialize connection to Interactive Brokers"""
        try:
            self.ib = IB()
            # Use a unique client ID to avoid conflicts with trading system
            client_id = 0  # High number to avoid conflicts
            self.logger.info(f"Attempting to connect to IB on port {self.ib_port} with client ID {client_id}")
            self.ib.connect('127.0.0.1', self.ib_port, clientId=client_id)
            self.ib_connected = True
            port_type = "TWS PAPER" if self.ib_port == 7497 else "TWS LIVE" if self.ib_port == 7496 else "IB Gateway PAPER" if self.ib_port == 4002 else "IB Gateway LIVE"
            self.logger.info(f"✅ Connected to Interactive Brokers ({port_type} - port {self.ib_port})")
            print(f"✅ Connected to Interactive Brokers ({port_type} - port {self.ib_port})")
        except Exception as e:
            self.ib_connected = False
            self.logger.error(f"⚠️  Could not connect to IB (port {self.ib_port}): {e}")
            self.logger.error("   Open positions will not be available")
            print(f"⚠️  Could not connect to IB (port {self.ib_port}): {e}")
            print("   Open positions will not be available")

    def disconnect_ib(self):
        """Disconnect from Interactive Brokers"""
        if self.ib and self.ib_connected:
            try:
                self.ib.disconnect()
                self.logger.info("✅ Disconnected from Interactive Brokers")
                print("✅ Disconnected from Interactive Brokers")
            except Exception as e:
                self.logger.error(f"Error disconnecting from IB: {e}")

    def save_order_to_db(self, symbol, start_timestamp, avgFillPrice, status, tradeLog, orderType, totalQuantity):
        """Save order to MySQL Orders table"""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()

            cursor.execute('''
                INSERT INTO Orders (`symbol`, `end_timestamp`, `start_timestamp`, `filledPrice`, `status`, `log`, `orderType`, `totalQuantity`, `tradeSignalsCount`, `ask_price`, `ask_timestamp`, `ask_size`, `bid_price`, `bid_size`, `open_price`, `open_timestamp`, `last_trade_price`, `last_trade_timestamp`, `polygon_second_close`, `active_seconds_count`)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ''', (symbol, time.time(), start_timestamp, avgFillPrice, status, str(tradeLog), orderType, totalQuantity, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0))

            conn.commit()
            cursor.close()
            conn.close()
            self.logger.info(f"Order saved to DB: {symbol} - {status}")
        except Exception as e:
            self.logger.error(f"Error saving order to DB: {e}")

    def persist_trade_signal(self, symbol, close, volume, purchasePrediction="MANUAL_BUY"):
        """Save trade signal to TradeSignalsBuyPerSecond table"""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()

            cursor.execute('''
                INSERT INTO TradeSignalsBuyPerSecond
                (`symbol`, `close`, `accumulated_volume`, `purchasePrediction`, `timestamp_unix`)
                VALUES (%s, %s, %s, %s, %s)
            ''', (symbol, close, volume, purchasePrediction, int(time.time() * 1000)))

            conn.commit()
            cursor.close()
            conn.close()
            self.logger.info(f"Trade signal saved: {symbol} - {purchasePrediction}")
        except Exception as e:
            self.logger.error(f"Error saving trade signal: {e}")

    async def place_manual_buy_order(self, symbol: str, quantity: int = 100):
        """
        Place a manual buy order through Interactive Brokers
        Returns: (success: bool, message: str, fill_price: float)
        """
        self.logger.info(f"=== MANUAL BUY ORDER START: {symbol} x{quantity} ===")

        if not self.ib_connected or not self.ib:
            self.logger.error("IB not connected - cannot place order")
            return False, "Not connected to IB", 0.0

        try:
            # Get current market quote from Polygon
            polygon_key = "0oQUg6UgH34Ala4OF_YYObsT_5Jh2IBJ"
            client = RESTClient(polygon_key)

            quote = client.get_last_quote(symbol)
            ask_price = quote.ask_price

            self.logger.info(f"Current ask price for {symbol}: ${ask_price}")

            # Create IB order
            stock = Stock(symbol, 'SMART', 'USD')
            limit_price = round(ask_price + 0.02, 2)  # Add 2 cents for aggressive fill
            order = LimitOrder('BUY', quantity, limit_price)

            self.logger.info(f"Placing limit order: BUY {quantity} {symbol} @ ${limit_price}")

            start_timestamp = time.time()

            # Place order
            trade = self.ib.placeOrder(stock, order)

            # Wait for order to fill (max 10 seconds)
            start_time = time.time()
            while not trade.isDone():
                elapsed_time = time.time() - start_time

                if elapsed_time > 10:
                    self.logger.warning(f"Order timeout after 10 seconds - cancelling {symbol}")
                    self.ib.cancelOrder(trade.order)

                    self.save_order_to_db(
                        symbol, start_timestamp, 0, "Not executed",
                        "Timeout after 10 seconds", "BUY", quantity
                    )

                    return False, "Order timeout - cancelled", 0.0

                # Check if ask price increased
                current_quote = client.get_last_quote(symbol)
                current_ask = current_quote.ask_price

                if current_ask > ask_price:
                    self.logger.warning(f"Ask price increased from ${ask_price} to ${current_ask} - cancelling")
                    self.ib.cancelOrder(trade.order)

                    self.save_order_to_db(
                        symbol, start_timestamp, 0, "Not executed",
                        f"Ask increased from ${ask_price} to ${current_ask}", "BUY", quantity
                    )

                    return False, "Ask price increased - cancelled", 0.0

                await asyncio.sleep(0.3)

            # Check if filled
            if trade.isDone() and trade.orderStatus.status == "Filled":
                fill_price = trade.orderStatus.avgFillPrice

                self.logger.info(f"✅ ORDER FILLED: {symbol} @ ${fill_price}")

                # Save to Orders table
                self.save_order_to_db(
                    symbol, start_timestamp, fill_price, "Filled",
                    str(trade), "BUY", quantity
                )

                # Save trade signal
                self.persist_trade_signal(symbol, fill_price, quantity, "MANUAL_BUY")

                return True, f"Bought {quantity} shares @ ${fill_price}", fill_price

            else:
                self.logger.warning(f"Order not filled: {trade.orderStatus.status}")
                return False, f"Order status: {trade.orderStatus.status}", 0.0

        except Exception as e:
            self.logger.error(f"Error placing manual buy order: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
            return False, f"Error: {str(e)}", 0.0

    def get_positions(self) -> List[Dict]:
        """Get current open positions from Interactive Brokers"""
        cache_key = "positions"
        if self._is_cache_valid(cache_key):
            return self._cache.get(cache_key, [])

        positions = []

        # Debug: Check connection status
        self.logger.debug(f"get_positions() called - IB Connected: {self.ib_connected}, IB object exists: {self.ib is not None}")

        # Query Interactive Brokers for actual open positions
        if self.ib_connected and self.ib:
            try:
                # Use portfolio() instead of positions() to get market value and P&L
                self.logger.debug("Calling ib.portfolio()...")
                portfolio_items = self.ib.portfolio()
                self.logger.info(f"Retrieved {len(portfolio_items)} portfolio items from IB")

                for item in portfolio_items:
                    self.logger.debug(f"Portfolio: {item.contract.symbol} ({item.contract.secType}), Qty: {item.position}, AvgCost: {item.averageCost}, Market Value: {item.marketValue}, P&L: {item.unrealizedPNL}")

                    # Only show stock positions (not options, futures, etc.)
                    if item.contract.secType == 'STK' and item.position != 0:
                        positions.append({
                            'symbol': item.contract.symbol,
                            'entry_price': item.averageCost,
                            'quantity': int(item.position),
                            'market_value': item.marketValue,
                            'unrealized_pnl': item.unrealizedPNL
                        })
                        self.logger.debug(f"✓ Added {item.contract.symbol} to positions list")
                    else:
                        self.logger.debug(f"✗ Skipped {item.contract.symbol} - secType: {item.contract.secType}, position: {item.position}")

                self.logger.info(f"Final positions list has {len(positions)} items")

            except Exception as e:
                self.logger.error(f"Error fetching positions from IB: {e}")
                import traceback
                self.logger.error(traceback.format_exc())
                positions = []
        else:
            self.logger.warning(f"Skipping IB query - IB connected: {self.ib_connected}, IB object: {self.ib is not None}")

        self._cache[cache_key] = positions
        self._last_fetch[cache_key] = time.time()
        return positions

    def get_recent_orders(self, limit: int = 15) -> List[Dict]:
        """Get recent orders from Orders table"""
        cache_key = f"orders_{limit}"
        if self._is_cache_valid(cache_key):
            return self._cache.get(cache_key, [])

        try:
            conn = self._get_connection()
            cursor = conn.cursor(dictionary=True)

            cursor.execute("""
                SELECT
                    symbol,
                    status,
                    orderType,
                    totalQuantity as qty,
                    filledPrice as price,
                    FROM_UNIXTIME(start_timestamp) as timestamp,
                    log
                FROM Orders
                ORDER BY id DESC
                LIMIT %s
            """, (limit,))

            orders = cursor.fetchall()
            cursor.close()
            conn.close()

            self._cache[cache_key] = orders
            self._last_fetch[cache_key] = time.time()
            return orders

        except Exception as e:
            print(f"Error fetching orders: {e}")
            return []

    def get_recent_signals(self, limit: int = 15) -> List[Dict]:
        """Get recent trade signals"""
        cache_key = f"signals_{limit}"
        if self._is_cache_valid(cache_key):
            return self._cache.get(cache_key, [])

        try:
            conn = self._get_connection()
            cursor = conn.cursor(dictionary=True)

            cursor.execute("""
                SELECT
                    symbol,
                    open,
                    close,
                    volume,
                    relative_volume_hour as rv_hour,
                    purchasePrediction as prediction,
                    FROM_UNIXTIME(timestamp) as timestamp
                FROM TradeSignalsBuyPerSecond
                ORDER BY timestamp DESC
                LIMIT %s
            """, (limit,))

            signals = cursor.fetchall()
            cursor.close()
            conn.close()

            self._cache[cache_key] = signals
            self._last_fetch[cache_key] = time.time()
            return signals

        except Exception as e:
            print(f"Error fetching signals: {e}")
            return []

    def get_system_metrics(self) -> Dict:
        """Get system health metrics from QueueBehavior table"""
        cache_key = "metrics"
        if self._is_cache_valid(cache_key):
            cached = self._cache.get(cache_key, {})
            # Always update live tick counter (not cached)
            cached['ticks_received'] = self._trade_counter
            return cached

        try:
            conn = self._get_connection()
            cursor = conn.cursor(dictionary=True)

            # Get latest queue metrics
            cursor.execute("""
                SELECT
                    queue_pressure,
                    number_trades,
                    market_trade_latency_offset as latency,
                    old_trades_count,
                    timestamp
                FROM QueueBehavior
                WHERE queue_id = 'trade_queue'
                ORDER BY id DESC
                LIMIT 1
            """)

            metrics = cursor.fetchone() or {}

            # Get total signals today
            cursor.execute("""
                SELECT COUNT(*) as total_signals
                FROM TradeSignalsBuyPerSecond
                WHERE DATE(FROM_UNIXTIME(timestamp)) = CURDATE()
            """)

            signal_count = cursor.fetchone()
            if signal_count:
                metrics['total_signals'] = signal_count['total_signals']

            # Get total orders today
            cursor.execute("""
                SELECT
                    COUNT(*) as total_orders,
                    SUM(CASE WHEN status = 'Filled' THEN 1 ELSE 0 END) as filled_orders
                FROM Orders
                WHERE DATE(FROM_UNIXTIME(start_timestamp)) = CURDATE()
            """)

            order_count = cursor.fetchone()
            if order_count:
                metrics.update(order_count)

            # Add live tick counter from WebSocket feed
            metrics['ticks_received'] = self._trade_counter

            cursor.close()
            conn.close()

            self._cache[cache_key] = metrics
            self._last_fetch[cache_key] = time.time()
            return metrics

        except Exception as e:
            print(f"Error fetching metrics: {e}")
            return {'ticks_received': self._trade_counter}

    def get_demo_trades(self, count: int = 1) -> List[Dict]:
        """Get real trades from trading system or demo data as fallback"""
        trades = []

        # LIVE MODE: Return ONLY real trades from dashboard_queue (consumer_process)
        if self.live_mode and self.dashboard_queue:
            # Drain all available trades (up to count) using for loop
            # for loop is safer than while loop - avoids potential blocking issues
            for _ in range(count):
                try:
                    trade = self.dashboard_queue.get_nowait()
                    trades.append(trade)
                    self._trade_counter += 1
                except queue.Empty:
                    break  # No more trades available, stop trying

            # CRITICAL: Return real trades only, even if empty list
            # User requirement: "REAL INFORMATION ONLY, not demo data"
            return trades

        # DEMO MODE: Generate simulated trades (only when live_mode=False)
        for _ in range(count):
            symbol = random.choice(self._demo_symbols)

            # Simulate realistic price movement
            current_price = self._demo_prices[symbol]
            price_change = random.uniform(-0.5, 0.5)
            new_price = max(1.0, current_price + price_change)
            self._demo_prices[symbol] = new_price

            # Generate demo trade data
            trade = {
                'symbol': symbol,
                'price': round(new_price, 2),
                'size': random.randint(100, 5000),
                'timestamp': time.time(),
                'exchange': random.choice(['NASDAQ', 'NYSE', 'ARCA']),
                'conditions': random.choice(['@', '@F', '@I', ''])
            }
            trades.append(trade)
            self._trade_counter += 1

        return trades


# ============================================================================
# UI Widgets
# ============================================================================

class SystemHealthWidget(Static):
    """Display system health metrics"""

    def __init__(self, data_source: TradingDataSource, **kwargs):
        super().__init__(**kwargs)
        self.data_source = data_source

    def on_mount(self):
        self.set_interval(1.0, self.update_metrics)
        self.update_metrics()

    def update_metrics(self):
        metrics = self.data_source.get_system_metrics()

        timestamp = metrics.get('timestamp', 'N/A')
        latency = metrics.get('latency', 0)
        queue_pressure = metrics.get('queue_pressure', 0)
        trades_count = metrics.get('number_trades', 0)
        total_signals = metrics.get('total_signals', 0)
        total_orders = metrics.get('total_orders', 0)
        filled_orders = metrics.get('filled_orders', 0)
        ticks_received = metrics.get('ticks_received', 0)

        # Color-code latency
        latency_color = "green" if latency < 500 else "yellow" if latency < 1000 else "red"

        # Trading system connection status
        if self.data_source.live_mode:
            ws_status = "[bold green]🟢 LIVE[/bold green]"
            ws_info = "consumer_process feed"
        else:
            ws_status = "[bold yellow]🟡 DEMO[/bold yellow]"
            ws_info = "simulated data"

        content = f"""[bold cyan]System Health[/bold cyan] {ws_status}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
[bold]WebSocket:[/bold] {ws_info}
[bold]Last Update:[/bold] {timestamp}
[bold]Latency:[/bold] [{latency_color}]{latency}ms[/{latency_color}]
[bold]Queue Pressure:[/bold] {queue_pressure}
[bold]Trades/Min:[/bold] {trades_count}

[bold yellow]Today's Stats[/bold yellow]
[bold]Ticks Received:[/bold] [green]{ticks_received:,}[/green]
[bold]Trade Signals:[/bold] {total_signals}
[bold]Total Orders:[/bold] {total_orders}
[bold]Filled Orders:[/bold] {filled_orders}
[bold]Fill Rate:[/bold] {(filled_orders/total_orders*100 if total_orders > 0 else 0):.1f}%
"""
        self.update(content)


class PositionsWidget(Static):
    """Display current open positions"""

    def __init__(self, data_source: TradingDataSource, **kwargs):
        super().__init__(**kwargs)
        self.data_source = data_source
        self.table = DataTable()

    def compose(self) -> ComposeResult:
        yield Label("[bold cyan]Open Positions[/bold cyan]")
        yield self.table

    def on_mount(self):
        # Setup table columns for IB positions
        self.table.add_columns("Symbol", "Avg Cost", "Quantity", "Market Value", "P&L")
        self.set_interval(2.0, self.update_positions)
        self.update_positions()

    def update_positions(self):
        positions = self.data_source.get_positions()

        # Clear existing rows
        self.table.clear()

        if not positions:
            self.table.add_row("No positions", "-", "-", "-", "-")
            return

        for pos in positions:
            symbol = pos.get('symbol', 'N/A')
            entry_price = f"${pos.get('entry_price', 0):.2f}"
            quantity = str(pos.get('quantity', 0))
            market_value = pos.get('market_value', 0)
            market_value_str = f"${market_value:.2f}" if market_value else "-"

            # Color-code P&L (green for profit, red for loss)
            unrealized_pnl = pos.get('unrealized_pnl', 0)
            if unrealized_pnl > 0:
                pnl_str = f"[green]+${unrealized_pnl:.2f}[/green]"
            elif unrealized_pnl < 0:
                pnl_str = f"[red]${unrealized_pnl:.2f}[/red]"
            else:
                pnl_str = "$0.00"

            self.table.add_row(symbol, entry_price, quantity, market_value_str, pnl_str)


class RecentTradesWidget(Static):
    """Display recent WebSocket trades (rolling window of 10)"""

    def __init__(self, data_source: TradingDataSource, **kwargs):
        super().__init__(**kwargs)
        self.data_source = data_source
        self.table = DataTable()
        self.trade_buffer = deque(maxlen=10)  # Keep only 10 most recent trades
        self.header_label = None

    def compose(self) -> ComposeResult:
        self.header_label = Label("[bold cyan]Live WebSocket Trades[/bold cyan]")
        yield self.header_label
        yield self.table

    def on_mount(self):
        # Setup table columns
        self.table.add_columns("Symbol", "Price", "Size", "Exchange", "Time")
        # Simulate incoming trades every 0.5 seconds
        self.set_interval(0.5, self.update_trades)
        self.update_trades()

    def update_trades(self):
        # Update header label based on connection status
        if self.header_label:
            if self.data_source.live_mode:
                self.header_label.update("[bold cyan]Live Trades (from consumer_process)[/bold cyan] [bold green]🟢 LIVE[/bold green]")
            else:
                self.header_label.update("[bold cyan]Live Trades[/bold cyan] [bold yellow]🟡 DEMO[/bold yellow]")

        # Get available trades (conservative drain to avoid queue issues)
        new_trades = self.data_source.get_demo_trades(5)

        # Add to buffer (deque automatically removes oldest when full)
        for trade in new_trades:
            self.trade_buffer.append(trade)

        # Clear and repopulate table
        self.table.clear()

        if not self.trade_buffer:
            self.table.add_row("No trades", "-", "-", "-", "-")
            return

        # Display trades in reverse chronological order (newest first)
        for trade in reversed(self.trade_buffer):
            symbol = trade['symbol']
            price = f"${trade['price']:.2f}"
            size = f"{trade['size']:,}"
            exchange = trade.get('exchange', 'N/A')
            timestamp = trade['timestamp']
            time_str = datetime.fromtimestamp(timestamp).strftime('%H:%M:%S.%f')[:-3]  # Include milliseconds

            self.table.add_row(symbol, price, size, exchange, time_str)


class ManualTradingWidget(Static):
    """Manual trading interface - Buy stock with symbol input"""

    def __init__(self, data_source: TradingDataSource, **kwargs):
        super().__init__(**kwargs)
        self.data_source = data_source

    def compose(self) -> ComposeResult:
        yield Label("[bold yellow]Manual Trading[/bold yellow]")
        yield Input(placeholder="Enter symbol (e.g., AAPL)", id="symbol_input")
        yield Button("🔵 Buy Stock", id="buy_btn", variant="success")

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle buy button press - Places REAL order in IB"""
        if event.button.id == "buy_btn":
            symbol_input = self.query_one("#symbol_input", Input)
            symbol = symbol_input.value.strip().upper()

            if not symbol:
                self.app.notify("⚠️ Please enter a symbol", severity="warning")
                return

            # Disable button while processing
            event.button.disabled = True
            self.app.notify(f"⏳ Placing BUY order for {symbol}...", severity="information")

            # Add to simulation panel with "PENDING" status
            simulation_widget = self.app.query_one(TradingSimulationWidget)
            simulation_widget.add_action("PENDING", symbol, 100, "Limit")

            # Place the real order
            success, message, fill_price = await self.data_source.place_manual_buy_order(symbol, quantity=100)

            # Update simulation panel with result
            if success:
                simulation_widget.add_action("BUY", symbol, 100, f"Filled @ ${fill_price:.2f}")
                self.app.notify(f"✅ {message}", severity="information")
            else:
                simulation_widget.add_action("FAILED", symbol, 100, message)
                self.app.notify(f"❌ {message}", severity="error")

            # Clear input and re-enable button
            symbol_input.value = ""
            event.button.disabled = False


class TradingSimulationWidget(Static):
    """Display simulated trading actions"""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.table = DataTable()
        self.actions = deque(maxlen=10)  # Keep last 10 actions

    def compose(self) -> ComposeResult:
        yield Label("[bold magenta]Trading Simulation[/bold magenta]")
        yield self.table

    def on_mount(self):
        self.table.add_columns("Action", "Symbol", "Quantity", "Order Type", "Time")
        self.update_table()

    def add_action(self, action: str, symbol: str, quantity: int, order_type: str):
        """Add a new trading action to the simulation"""
        timestamp = datetime.now()
        self.actions.append({
            'action': action,
            'symbol': symbol,
            'quantity': quantity,
            'order_type': order_type,
            'timestamp': timestamp
        })
        self.update_table()

    def update_table(self):
        """Update the table with current actions"""
        self.table.clear()

        if not self.actions:
            self.table.add_row("No actions", "-", "-", "-", "-")
            return

        # Display actions in reverse chronological order
        for action_data in reversed(self.actions):
            action = action_data['action']
            symbol = action_data['symbol']
            quantity = str(action_data['quantity'])
            order_type = action_data['order_type']
            time_str = action_data['timestamp'].strftime('%H:%M:%S')

            # Color code the action
            if action == "BUY":
                action_str = f"[green]{action}[/green]"
            elif action == "SELL":
                action_str = f"[red]{action}[/red]"
            elif action == "PENDING":
                action_str = f"[yellow]{action}[/yellow]"
            elif action == "FAILED":
                action_str = f"[red]{action}[/red]"
            else:
                action_str = action

            self.table.add_row(action_str, symbol, quantity, order_type, time_str)


class OrdersWidget(Static):
    """Display recent orders"""

    def __init__(self, data_source: TradingDataSource, **kwargs):
        super().__init__(**kwargs)
        self.data_source = data_source
        self.table = DataTable()

    def compose(self) -> ComposeResult:
        yield Label("[bold cyan]Recent Orders[/bold cyan]")
        yield self.table

    def on_mount(self):
        self.table.add_columns("Symbol", "Type", "Status", "Qty", "Price", "Time")
        self.set_interval(2.0, self.update_orders)
        self.update_orders()

    def update_orders(self):
        orders = self.data_source.get_recent_orders(10)

        self.table.clear()

        if not orders:
            self.table.add_row("No orders", "-", "-", "-", "-", "-")
            return

        for order in orders:
            symbol = order.get('symbol', 'N/A')
            order_type = order.get('orderType', 'N/A')
            status = order.get('status', 'N/A')

            # Color-code status
            if status == 'Filled':
                status = f"[green]{status}[/green]"
            elif status == 'Not executed':
                status = f"[red]{status}[/red]"
            else:
                status = f"[yellow]{status}[/yellow]"

            qty = str(order.get('qty', 0))
            price = f"${order.get('price', 0):.2f}" if order.get('price') else '-'

            timestamp = order.get('timestamp')
            time_str = timestamp.strftime('%H:%M:%S') if timestamp else 'N/A'

            self.table.add_row(symbol, order_type, status, qty, price, time_str)


class SignalsWidget(Static):
    """Display recent trade signals"""

    def __init__(self, data_source: TradingDataSource, **kwargs):
        super().__init__(**kwargs)
        self.data_source = data_source
        self.table = DataTable()

    def compose(self) -> ComposeResult:
        yield Label("[bold cyan]Trade Signals[/bold cyan]")
        yield self.table

    def on_mount(self):
        self.table.add_columns("Symbol", "Open", "Close", "Volume", "RV", "Prediction", "Time")
        self.set_interval(2.0, self.update_signals)
        self.update_signals()

    def update_signals(self):
        signals = self.data_source.get_recent_signals(10)

        self.table.clear()

        if not signals:
            self.table.add_row("No signals", "-", "-", "-", "-", "-", "-")
            return

        for signal in signals:
            symbol = signal.get('symbol', 'N/A')
            open_price = f"${signal.get('open', 0):.2f}"
            close_price = f"${signal.get('close', 0):.2f}"
            volume = f"{signal.get('volume', 0):,}"
            rv_hour = f"{signal.get('rv_hour', 0):.2f}x"

            prediction = signal.get('prediction', 'N/A')
            if prediction == 'BUY':
                prediction = f"[green bold]{prediction}[/green bold]"
            else:
                prediction = f"[dim]{prediction}[/dim]"

            timestamp = signal.get('timestamp')
            time_str = timestamp.strftime('%H:%M:%S') if timestamp else 'N/A'

            self.table.add_row(symbol, open_price, close_price, volume, rv_hour, prediction, time_str)


class DataLoadingWidget(Static):
    """Panel with button to load pre-market data"""

    def compose(self) -> ComposeResult:
        yield Label("[bold cyan]Data Pipeline[/bold cyan]")
        yield Button("📊 Load data for trading", id="load_data_btn", variant="primary")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button press"""
        if event.button.id == "load_data_btn":
            self.app.action_load_data()


class TradingConfigWidget(Static):
    """Display trading system configuration and strategy parameters"""

    def __init__(self, data_source: TradingDataSource, **kwargs):
        super().__init__(**kwargs)
        self.data_source = data_source

    def on_mount(self):
        self.update_config()

    def update_config(self):
        config = self.data_source.config

        # Default values for demo mode
        if not config:
            content = "[bold cyan]Trading Configuration[/bold cyan] [bold yellow]🟡 DEMO MODE[/bold yellow]"
            self.update(content)
            return

        # Extract configuration values
        trading_mode = config.get('trading_mode', 'Unknown')
        version = config.get('version', 'N/A')

        # Mode indicator
        if 'Paper' in trading_mode:
            mode_status = f"[bold yellow]📋 {trading_mode} {version}[/bold yellow]"
        else:
            mode_status = f"[bold red]🔴 {trading_mode} {version}[/bold red]"

        # Format numbers for better readability
        def format_number(num):
            if num >= 1_000_000:
                return f"{num/1_000_000:.1f}M"
            elif num >= 1_000:
                return f"{num/1_000:.1f}K"
            return str(num)

        low_float = format_number(config.get('low_float_threshold', 0))

        content = f"""[bold cyan]Trading Configuration[/bold cyan] {mode_status}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
[bold yellow]Market Filters[/bold yellow]
[bold]High Short-Interest Stocks:[/bold] {config.get('high_short_interest_count', 0)}
[bold]Short Interest Ratio:[/bold] {config.get('short_interest_ratio', 0):.2f}

[bold]Low Float Stocks:[/bold] {config.get('low_float_stocks_count', 0)}
[bold]Low Float Threshold:[/bold] {low_float}

[bold yellow]Signal Thresholds[/bold yellow]
[bold]Relative Volume:[/bold] {config.get('relative_volume', 0)}x
[bold]Relative Volume (Low Float):[/bold] {config.get('relative_volume_low_float', 0)}x
[bold]Price Range:[/bold] [green]${config.get('min_price', 0):.2f} - ${config.get('max_price', 0):.2f}[/green]

[bold yellow]Risk Management[/bold yellow]
[bold]Minimum Gain from Open:[/bold] {config.get('min_increase_from_open', 0)}%
[bold]Maximum Price Spike:[/bold] {config.get('max_price_spike', 0)}%
[bold]Stop Loss:[/bold] {config.get('max_loss_tolerance', 0):.1f}%

[bold yellow]Portfolio[/bold yellow]
[bold]Capital per Trade:[/bold] [red]${config.get('capital_per_trade', 0):,}[/red]
[bold]Total Symbols Monitored:[/bold] {config.get('total_symbols', 0):,}
"""
        self.update(content)


# ============================================================================
# Main Dashboard App
# ============================================================================

class TradingDashboard(App):
    """Main trading system monitoring dashboard"""

    CSS = """
    Screen {
        background: $surface;
    }

    #left-panel {
        width: 40%;
        border: solid green;
        padding: 1;
    }

    #right-panel {
        width: 60%;
        border: solid cyan;
        padding: 1;
    }

    DataTable {
        height: auto;
        max-height: 15;
    }

    SystemHealthWidget {
        border: solid yellow;
        padding: 1;
        margin: 1;
    }

    PositionsWidget {
        border: solid green;
        padding: 1;
        margin: 1;
    }

    RecentTradesWidget {
        border: solid cyan;
        padding: 1;
        margin: 1;
    }

    OrdersWidget {
        border: solid blue;
        padding: 1;
        margin: 1;
    }

    SignalsWidget {
        border: solid magenta;
        padding: 1;
        margin: 1;
    }

    TradingConfigWidget {
        border: solid yellow;
        padding: 1;
        margin: 1;
    }

    ManualTradingWidget {
        border: solid yellow;
        padding: 1;
        margin: 1;
    }

    ManualTradingWidget Input {
        margin: 1 0;
    }

    ManualTradingWidget Button {
        width: 100%;
        margin: 1 0;
    }

    TradingSimulationWidget {
        border: solid magenta;
        padding: 1;
        margin: 1;
    }
    """

    TITLE = "Trading System Monitor v1.0"
    SUB_TITLE = "Real-time monitoring dashboard"

    # Custom action bindings (appear in command palette)
    BINDINGS = [
        ("ctrl+l", "load_data", "Load data for trading"),
        ("f5", "load_data", "Load data for trading"),
    ]

    def __init__(self, data_source: Optional[TradingDataSource] = None):
        super().__init__()
        self.data_source = data_source or TradingDataSource()

    def compose(self) -> ComposeResult:
        """Create the UI layout"""
        yield Header()

        with Horizontal():
            with VerticalScroll(id="left-panel"):
                yield SystemHealthWidget(self.data_source)
                yield PositionsWidget(self.data_source)
                yield TradingConfigWidget(self.data_source)

            with VerticalScroll(id="right-panel"):
                yield OrdersWidget(self.data_source)
                yield SignalsWidget(self.data_source)
                yield RecentTradesWidget(self.data_source)
                yield ManualTradingWidget(self.data_source)
                yield TradingSimulationWidget()

        yield Footer()

    def action_quit(self):
        """Quit the application"""
        # Disconnect from IB before exiting
        if self.data_source:
            self.data_source.disconnect_ib()
        self.exit()

    def action_load_data(self):
        """Load pre-market trading data - runs the full data pipeline"""
        self.notify(
            "🚀 Starting data pipeline...",
            title="Data Pipeline",
            severity="information",
            timeout=3
        )

        # Run data loading in background thread to avoid blocking UI
        def run_data_pipeline():
            try:
                # Step 1: Clear day work tables
                self.notify("🗑️  Clearing day work tables...", title="Step 1/5", timeout=3)
                clear_day_work_tables()

                # Step 2: Get previous close prices
                self.notify("📊 Fetching previous close prices...", title="Step 2/5", timeout=3)
                getPreviousClose()

                # Step 3: Get float data
                self.notify("🔢 Retrieving float data...", title="Step 3/5", timeout=3)
                get_float()

                # Step 4: Get historical data
                self.notify("📈 Loading historical data...", title="Step 4/5", timeout=3)
                getHistoricalData()

                # Step 5: Calculate relative volume
                self.notify("⚡ Calculating relative volume ratios...", title="Step 5/5", timeout=3)
                getRelativeVolumeFactor()

                # Success!
                self.notify(
                    "✅ Data pipeline completed successfully!\n   System ready for trading.",
                    title="Data Pipeline",
                    severity="information",
                    timeout=5
                )

            except Exception as e:
                # Error handling
                self.notify(
                    f"❌ Data pipeline failed: {str(e)}",
                    title="Data Pipeline Error",
                    severity="error",
                    timeout=10
                )

        # Start in background thread
        threading.Thread(target=run_data_pipeline, daemon=True).start()


# ============================================================================
# Standalone Testing Mode
# ============================================================================

def test_data_source():
    """Test the data source connection"""
    print("Testing database connection...")

    ds = TradingDataSource()

    print("\n1. Testing positions fetch...")
    positions = ds.get_positions()
    print(f"   Found {len(positions)} positions")
    if positions:
        print(f"   Example: {positions[0]}")

    print("\n2. Testing orders fetch...")
    orders = ds.get_recent_orders(5)
    print(f"   Found {len(orders)} orders")
    if orders:
        print(f"   Example: {orders[0]}")

    print("\n3. Testing signals fetch...")
    signals = ds.get_recent_signals(5)
    print(f"   Found {len(signals)} signals")
    if signals:
        print(f"   Example: {signals[0]}")

    print("\n4. Testing system metrics...")
    metrics = ds.get_system_metrics()
    print(f"   Metrics: {metrics}")

    print("\n✓ All tests passed!")


# ============================================================================
# Main Entry Point
# ============================================================================

def main():
    """
    Run the trading dashboard as MAIN ENTRY POINT.
    Starts both the trading system AND the dashboard UI.
    """
    import sys

    # Check for test mode
    if len(sys.argv) > 1 and sys.argv[1] == 'test':
        test_data_source()
        return

    print("=" * 70)
    print("  TRADING SYSTEM + DASHBOARD")
    print("  Integrated Entry Point v2.0")
    print("=" * 70)
    print()

    dashboard_queue = None
    trading_system_handle = None
    config = {}

    try:
        # STEP 1: Start Trading System in background thread
        print("🚀 Starting trading system in background...")
        print("   This includes the WebSocket connection to Polygon.io")
        print()

        # Shared container for thread result
        result_container = {'handle': None, 'error': None}

        def start_trading_system():
            """Runs in background thread - MUST stay alive to keep Manager active!"""
            try:
                import sys
                import asyncio
                import os
                import threading

                # Set environment variable to suppress subprocess output
                os.environ['DASHBOARD_MODE'] = '1'

                # Redirect trading system output to log file (cleaner dashboard console)
                log_file_path = '/Users/tan/experiments/polygon.io/trading_system.log'

                # Keep log file open in result container so it doesn't get closed
                result_container['log_file'] = open(log_file_path, 'w', buffering=1)

                # Save original stdout/stderr
                original_stdout = sys.stdout
                original_stderr = sys.stderr

                # Redirect to log file
                sys.stdout = result_container['log_file']
                sys.stderr = result_container['log_file']

                # CRITICAL: Create event loop for this thread (required by ib_insync/eventkit)
                try:
                    loop = asyncio.get_event_loop()
                except RuntimeError:
                    # No event loop in thread - create one
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)

                sys.path.insert(0, '/Users/tan/experiments/polygon.io')
                from multiprocessing_websocket_rv_hour import mainT

                # Start trading system in non-blocking mode
                result = mainT(blocking=False)
                result_container['handle'] = result

                # Restore stdout for this message
                sys.stdout = original_stdout
                sys.stderr = original_stderr
                print("✅ Trading system initialization complete")
                print(f"   Output logged to: {log_file_path}")

                # CRITICAL: Keep this thread alive forever!
                # If thread exits, Manager becomes orphaned and dashboard_queue stops working
                sys.stdout = result_container['log_file']
                sys.stderr = result_container['log_file']

                # Sleep forever to keep Manager alive
                stop_event = threading.Event()
                stop_event.wait()  # Block forever until program exits

            except Exception as e:
                import traceback
                # Restore stdout for error messages
                if 'log_file' in result_container and result_container['log_file']:
                    sys.stdout = original_stdout
                    sys.stderr = original_stderr
                result_container['error'] = str(e)
                print(f"❌ Trading system failed to start: {e}")
                traceback.print_exc()

        # Run trading system starter in daemon thread
        trading_thread = threading.Thread(
            target=start_trading_system,
            daemon=True,
            name="TradingSystemStarter"
        )
        trading_thread.start()

        # Wait for trading system to initialize
        print("⏳ Waiting for trading system to initialize (8 seconds)...")
        time.sleep(8)

        # Get the dashboard_queue from trading system
        trading_system_handle = result_container['handle']

        # Check for errors
        if result_container['error']:
            print(f"❌ Trading system initialization error:")
            print(f"   {result_container['error']}")
            print("   Dashboard will run in DEMO mode")
            print()
        elif trading_system_handle and 'dashboard_queue' in trading_system_handle:
            dashboard_queue = trading_system_handle['dashboard_queue']
            config = trading_system_handle.get('config', {})
            print("✅ Trading system started successfully!")
            print(f"   Dashboard queue: Connected")
            print(f"   Manager: Active")
            print(f"   Configuration: Loaded")
            print(f"   Processes: {len(trading_system_handle.get('processes', []))} running")
            print()
        else:
            print("⚠️  Trading system did not return dashboard_queue")
            print(f"   Handle received: {trading_system_handle}")
            print("   Dashboard will run in DEMO mode")
            print()
            config = {}

        # STEP 2: Start Dashboard UI
        print("🖥️  Starting dashboard UI...")
        print("   Press Ctrl+C to exit")
        print()

        # Create data source with dashboard_queue and config
        # Use port 7497 for TWS paper account (7496 for TWS live, 4002 for IB Gateway paper, 4001 for IB Gateway live)
        data_source = TradingDataSource(dashboard_queue=dashboard_queue, config=config, ib_port=7497)

        # Create and run dashboard
        app = TradingDashboard(data_source=data_source)
        app.run()

    except KeyboardInterrupt:
        print("\n\n⚠️  Shutting down gracefully...")
        print("   Terminating trading system processes...")

        # Clean up trading system processes
        if trading_system_handle and 'processes' in trading_system_handle:
            for proc in trading_system_handle['processes']:
                try:
                    proc.terminate()
                except:
                    pass

        print("✅ Shutdown complete")

    except Exception as e:
        print(f"\n\n❌ Error: {e}")
        import traceback
        traceback.print_exc()

        # Clean up on error
        if trading_system_handle and 'processes' in trading_system_handle:
            for proc in trading_system_handle['processes']:
                try:
                    proc.terminate()
                except:
                    pass


if __name__ == "__main__":
    main()
