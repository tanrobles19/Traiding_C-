"""
WebSocket Dashboard - Simple Version
=====================================
Displays trades from an ALREADY RUNNING trading system.

The trading system must be started separately first.
This dashboard reads from the MySQL trades table.
"""

from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, Static, DataTable, Button
from textual.containers import Container, Vertical
from textual.reactive import reactive
from datetime import datetime
import mysql.connector
import threading
import time


class SimpleWebSocketDashboard(App):
    """Simple trade monitor that reads from MySQL"""

    CSS = """
    Screen {
        background: $surface;
    }

    #header_container {
        height: 5;
        background: $boost;
        padding: 1;
    }

    #status {
        color: $text;
        text-align: center;
    }

    #connect_button {
        margin: 1;
        width: 30;
    }

    #trades_container {
        height: 1fr;
        border: solid $primary;
        padding: 1;
    }

    DataTable {
        height: 1fr;
    }
    """

    TITLE = "WebSocket Trade Monitor"

    connected = reactive(False)
    trade_count = reactive(0)

    def __init__(self):
        super().__init__()
        self.db_connection = None
        self.monitor_thread = None
        self.last_trade_id = 0

    def compose(self) -> ComposeResult:
        """Create child widgets for the app"""
        yield Header()

        with Container(id="header_container"):
            yield Static("Status: Disconnected", id="status")
            yield Button("Connect WebSocket", id="connect_button", variant="success")

        with Vertical(id="trades_container"):
            yield Static("Real-Time Trades (from MySQL 'trades' table)", id="trades_header")
            yield DataTable(id="trades_table")

        yield Footer()

    def on_mount(self) -> None:
        """Configure the app when mounted"""
        table = self.query_one("#trades_table", DataTable)
        table.add_columns("ID", "Time", "Symbol", "Price", "Volume", "Exchange")
        table.cursor_type = "row"

        # Start UI update timer (2Hz refresh from database)
        self.set_interval(0.5, self.poll_database)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle Connect WebSocket button"""
        if event.button.id == "connect_button":
            if not self.connected:
                self.connect_to_database()

    def connect_to_database(self) -> None:
        """Connect to MySQL database"""
        try:
            self.db_connection = mysql.connector.connect(
                host="localhost",
                port=3306,
                user="root",
                password="E_I$S5PFri",
                database="histFinanData"
            )

            self.connected = True
            self.update_status("✅ Connected to MySQL")

            button = self.query_one("#connect_button", Button)
            button.disabled = True
            button.label = "Connected"

            self.notify("Connected to database - monitoring 'trades' table")

        except Exception as e:
            self.update_status(f"ERROR: {str(e)}")
            self.notify(f"Database connection failed: {str(e)}", severity="error")

    def poll_database(self) -> None:
        """Poll database for new trades (called every 0.5s)"""
        if not self.connected or not self.db_connection:
            return

        try:
            cursor = self.db_connection.cursor()

            # Get trades newer than last_trade_id
            query = """
                SELECT id, timestamp, symbol, close, volume, exchange
                FROM trades
                WHERE id > %s
                ORDER BY id ASC
                LIMIT 100
            """
            cursor.execute(query, (self.last_trade_id,))
            rows = cursor.fetchall()

            if rows:
                table = self.query_one("#trades_table", DataTable)

                for row in rows:
                    trade_id, timestamp, symbol, price, volume, exchange = row

                    # Format timestamp
                    if isinstance(timestamp, str):
                        time_str = timestamp.split()[1] if ' ' in timestamp else timestamp[:8]
                    else:
                        time_str = timestamp.strftime('%H:%M:%S')

                    # Add row to table
                    table.add_row(
                        str(trade_id),
                        time_str,
                        symbol,
                        f"${price:.2f}",
                        str(volume),
                        str(exchange or 'N/A'),
                        key=str(trade_id)
                    )

                    self.trade_count += 1
                    self.last_trade_id = max(self.last_trade_id, trade_id)

                # Limit table to last 500 trades
                if table.row_count > 500:
                    first_row_key = list(table.rows.keys())[0]
                    table.remove_row(first_row_key)

            cursor.close()

        except Exception as e:
            self.update_status(f"ERROR: {str(e)}")

    def update_status(self, message: str) -> None:
        """Update status text"""
        status = self.query_one("#status", Static)
        status.update(f"Status: {message}")

    def watch_trade_count(self, count: int) -> None:
        """Update status with trade count"""
        if self.connected:
            self.update_status(f"✅ Connected | Trades: {count:,}")

    def on_unmount(self) -> None:
        """Cleanup when app closes"""
        if self.db_connection:
            self.db_connection.close()


def main():
    """Entry point for dashboard"""
    app = SimpleWebSocketDashboard()
    app.run()


if __name__ == "__main__":
    main()
