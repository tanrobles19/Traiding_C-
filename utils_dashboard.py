"""
Trading System Utilities Dashboard
===================================
Utility functions for data preparation and system maintenance.

Run: python3 utils_dashboard.py
"""

from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, Static, Label, Button
from textual.containers import Container, Vertical, VerticalScroll
from textual.reactive import reactive
import threading
import logging
from datetime import datetime, timedelta

# Setup logger
logger = logging.getLogger(__name__)


def get_last_n_business_days(n=15):
    """
    Get the date range for the last N business days.
    Returns (init_date, end_date, init_date_display, end_date_display) where:
    - end_date = yesterday (last business day)
    - init_date = N business days before end_date
    """
    today = datetime.now()

    # Get yesterday
    current = today - timedelta(days=1)

    # Find the last business day (yesterday, but skip weekends)
    while current.weekday() >= 5:  # 5=Saturday, 6=Sunday
        current -= timedelta(days=1)

    end_date = current

    # Count back n business days from end_date
    business_days_count = 0
    current = end_date

    while business_days_count < n:
        current -= timedelta(days=1)
        if current.weekday() < 5:  # Monday=0, Friday=4
            business_days_count += 1

    init_date = current

    # Format for API (YYYY-MM-DD)
    init_date_api = init_date.strftime("%Y-%m-%d")
    end_date_api = end_date.strftime("%Y-%m-%d")

    # Format for display (DD-MM-YYYY)
    init_date_display = init_date.strftime("%d-%m-%Y")
    end_date_display = end_date.strftime("%d-%m-%Y")

    return init_date_api, end_date_api, init_date_display, end_date_display


# Import data loading functions
from clean_db import clear_day_work_tables
from fetch_historycal_data_to_db import getHistoricalData
from relative_volume_ratio import getRelativeVolumeFactor
import mysql.connector
from trading_config import (
    get_symbols_from_database,
    MIN_PRICE_THRESHOLD,
    MAX_PRICE_THRESHOLD,
    FLOAT_THRESHOLD,
    MAX_LOSS_TOLERANCE_PER_TRADE,
    TRADE_CAPITAL,
    INCREASE_FROM_OPEN
)


class PipelineProgressWidget(Static):
    """Visual progress indicator for data pipeline steps"""

    # Reactive state for each step (pending, running, complete, error)
    step1_status = reactive("pending")
    step2_status = reactive("pending")
    step3_status = reactive("pending")

    # Detailed progress for steps (e.g., "Processing AAPL #50/1000")
    step2_detail = reactive("")
    step3_detail = reactive("")

    # Error messages for failed steps
    step1_error = reactive("")
    step2_error = reactive("")
    step3_error = reactive("")

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.steps = [
            {"name": "Clear day work tables", "status_var": "step1_status", "detail_var": None},
            {"name": "Load historical data → HistoryByMin", "status_var": "step2_status", "detail_var": "step2_detail"},
            {"name": "Calculate relative volume → RelativeVolumeRatioHour", "status_var": "step3_status", "detail_var": "step3_detail"},
        ]

    def get_status_icon(self, status: str) -> str:
        """Get icon for status"""
        icons = {
            "pending": "⏳",
            "running": "▶️",
            "complete": "✅",
            "error": "❌"
        }
        return icons.get(status, "⏳")

    def get_status_color(self, status: str) -> str:
        """Get color for status"""
        colors = {
            "pending": "dim",
            "running": "yellow bold",
            "complete": "green",
            "error": "red"
        }
        return colors.get(status, "dim")

    def render(self) -> str:
        """Render the pipeline progress"""
        lines = ["[bold cyan]Pipeline Progress[/bold cyan]", "━" * 50]

        for i, step in enumerate(self.steps, 1):
            status_var = step["status_var"]
            detail_var = step["detail_var"]
            status = getattr(self, status_var)
            icon = self.get_status_icon(status)
            color = self.get_status_color(status)
            name = step["name"]

            # Get detail if available
            detail = ""
            if detail_var:
                detail_text = getattr(self, detail_var, "")
                if detail_text:
                    detail = f" [dim]{detail_text}[/dim]"

            lines.append(f"[{color}]{icon} Step {i}/5: {name}{detail}[/{color}]")

            # Display error message if step failed
            if status == "error":
                error_var = f"step{i}_error"
                error_msg = getattr(self, error_var, "")
                if error_msg:
                    lines.append(f"[red]   ⚠️  Error: {error_msg}[/red]")

        return "\n".join(lines)

    def watch_step1_status(self, old, new): self.refresh()
    def watch_step2_status(self, old, new): self.refresh()
    def watch_step3_status(self, old, new): self.refresh()

    def watch_step2_detail(self, old, new): self.refresh()
    def watch_step3_detail(self, old, new): self.refresh()

    def watch_step1_error(self, old, new): self.refresh()
    def watch_step2_error(self, old, new): self.refresh()
    def watch_step3_error(self, old, new): self.refresh()

    def reset(self):
        """Reset all steps to pending"""
        self.step1_status = "pending"
        self.step2_status = "pending"
        self.step3_status = "pending"
        self.step2_detail = ""
        self.step3_detail = ""
        self.step1_error = ""
        self.step2_error = ""
        self.step3_error = ""


class ConfigurationInfoWidget(Static):
    """Display configuration variables used in the pipeline"""

    # Reactive state for configuration info
    symbol_count = reactive(0)
    symbol_range = reactive("")
    tables_cleaned = reactive("")
    float_threshold = reactive("")
    price_range = reactive("")
    date_range = reactive("")
    trade_capital = reactive("")
    max_loss = reactive("")
    increase_threshold = reactive("")

    def on_mount(self):
        """Load initial configuration from trading_config.py"""
        # Load configuration from database using centralized function
        try:
            db_connection = mysql.connector.connect(
                host="localhost",
                port=3306,
                user="root",
                password="E_I$S5PFri",
                database="histFinanData"
            )
            cursor = db_connection.cursor()

            # Get symbols using centralized function
            symbols = get_symbols_from_database(cursor)

            cursor.close()
            db_connection.close()

            # Update configuration display
            if symbols:
                self.symbol_count = len(symbols)
                if len(symbols) <= 10:
                    self.symbol_range = f"{', '.join(symbols)}"
                else:
                    first_5 = ', '.join(symbols[:5])
                    last_5 = ', '.join(symbols[-5:])
                    self.symbol_range = f"{first_5} ... {last_5}"

            # Set static configuration from trading_config.py
            self.float_threshold = f"< {FLOAT_THRESHOLD:,} shares"
            self.price_range = f"${MIN_PRICE_THRESHOLD:.2f} - ${MAX_PRICE_THRESHOLD:.2f}"
            self.trade_capital = f"${TRADE_CAPITAL:,.0f} per trade"
            loss_pct = (1 - MAX_LOSS_TOLERANCE_PER_TRADE) * 100
            self.max_loss = f"{loss_pct:.0f}% max loss per trade"
            self.increase_threshold = f"{INCREASE_FROM_OPEN}% minimum increase"

            # Query initial record counts for tables
            self._update_table_counts()

        except Exception as e:
            # If database not accessible yet, show config from code
            self.float_threshold = f"< {FLOAT_THRESHOLD:,} shares"
            self.price_range = f"${MIN_PRICE_THRESHOLD:.2f} - ${MAX_PRICE_THRESHOLD:.2f}"
            self.tables_cleaned = "No data yet"
            self.trade_capital = f"${TRADE_CAPITAL:,.0f} per trade"
            loss_pct = (1 - MAX_LOSS_TOLERANCE_PER_TRADE) * 100
            self.max_loss = f"{loss_pct:.0f}% max loss per trade"
            self.increase_threshold = f"{INCREASE_FROM_OPEN}% minimum increase"

    def _update_table_counts(self):
        """Query database for record counts in all relevant tables"""
        try:
            db_connection = mysql.connector.connect(
                host="localhost",
                port=3306,
                user="root",
                password="E_I$S5PFri",
                database="histFinanData"
            )
            cursor = db_connection.cursor()

            # Get counts for each table (only show relevant pipeline tables)
            cursor.execute("SELECT COUNT(*) FROM HistoryByMin")
            count_history = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM RelativeVolumeRatioHour")
            count_rv = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM minute_candlesticks")
            count_candles = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM trades")
            count_trades = cursor.fetchone()[0]

            cursor.close()
            db_connection.close()

            # Format with record counts (pipeline tables in logical order)
            self.tables_cleaned = (
                f"HistoryByMin = {count_history:,} (Step 4)\n"
                f"RelativeVolumeRatioHour = {count_rv:,} (Step 5)\n"
                f"minute_candlesticks = {count_candles:,} (intraday)\n"
                f"trades = {count_trades:,} (intraday)"
            )

        except Exception as e:
            self.tables_cleaned = "Tables: HistoryByMin, RelativeVolumeRatioHour, minute_candlesticks, trades"

    def render(self) -> str:
        """Render the configuration info"""
        lines = ["[bold yellow]Configuration & Results[/bold yellow]", "━" * 50]

        if self.symbol_count > 0:
            lines.append(f"[cyan]Symbols Processed:[/cyan] [white]{self.symbol_count}[/white]")

        if self.symbol_range:
            lines.append(f"[cyan]Symbol Range:[/cyan] [white]{self.symbol_range}[/white]")

        if self.float_threshold:
            lines.append(f"[cyan]Float Threshold:[/cyan] [white]{self.float_threshold}[/white]")

        if self.price_range:
            lines.append(f"[cyan]Price Range:[/cyan] [white]{self.price_range}[/white]")

        if self.trade_capital:
            lines.append(f"[cyan]Trade Capital:[/cyan] [white]{self.trade_capital}[/white]")

        if self.max_loss:
            lines.append(f"[cyan]Max Loss Tolerance:[/cyan] [white]{self.max_loss}[/white]")

        if self.increase_threshold:
            lines.append(f"[cyan]Increase Threshold:[/cyan] [white]{self.increase_threshold}[/white]")

        if self.date_range:
            lines.append(f"[cyan]Date Range:[/cyan] [white]{self.date_range}[/white]")

        if self.tables_cleaned:
            lines.append(f"[cyan]Database Status:[/cyan]")
            # Split multi-line table status and indent each line
            for line in self.tables_cleaned.split('\n'):
                lines.append(f"  [white]{line}[/white]")

        return "\n".join(lines)

    def watch_symbol_count(self, old, new): self.refresh()
    def watch_symbol_range(self, old, new): self.refresh()
    def watch_tables_cleaned(self, old, new): self.refresh()
    def watch_float_threshold(self, old, new): self.refresh()
    def watch_price_range(self, old, new): self.refresh()
    def watch_date_range(self, old, new): self.refresh()
    def watch_trade_capital(self, old, new): self.refresh()
    def watch_max_loss(self, old, new): self.refresh()
    def watch_increase_threshold(self, old, new): self.refresh()

    def reset(self):
        """Reset dynamic pipeline data, keep static configuration"""
        # Only reset date_range which changes per run
        # Keep static config: symbol_count, symbol_range, tables_cleaned, float_threshold, price_range
        self.date_range = ""


class PipelineExplanationWidget(Static):
    """Explains what Step 4 and Step 5 do"""

    def render(self) -> str:
        """Render the explanation"""
        lines = [
            "[bold cyan]Pipeline Details[/bold cyan]",
            "━" * 50,
            "",
            "[yellow]Step 4 - Load Historical Data[/yellow]",
            "Downloads historical hourly price and volume data from Polygon.io for",
            "the [bold]last 5 business days[/bold] (1 week) and persists it in [cyan]HistoryByMin[/cyan] table.",
            "",
            "[yellow]Step 5 - Calculate Relative Volume[/yellow]",
            "This historical data is used as the baseline for calculating relative",
            "volume. You need to know \"what is normal volume for this hour\" in order",
            "to detect when volume is abnormally high during real-time trading.",
        ]
        return "\n".join(lines)


class DataLoadingWidget(Static):
    """Panel with button to load pre-market data"""

    def compose(self) -> ComposeResult:
        yield Label("[bold cyan]Data Pipeline[/bold cyan]")
        yield Button("📊 Load data for trading", id="load_data_btn", variant="primary")
        yield PipelineProgressWidget(id="pipeline_progress")
        yield PipelineExplanationWidget(id="pipeline_explanation")
        yield ConfigurationInfoWidget(id="config_info")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button press"""
        if event.button.id == "load_data_btn":
            # Reset progress before starting
            progress = self.query_one("#pipeline_progress", PipelineProgressWidget)
            progress.reset()

            # Reset configuration info
            config_info = self.query_one("#config_info", ConfigurationInfoWidget)
            config_info.reset()

            # Start the pipeline
            self.app.action_load_data()


class UtilsDashboard(App):
    """Utilities dashboard for system maintenance and data preparation"""

    CSS = """
    Screen {
        background: $surface;
    }

    DataLoadingWidget {
        border: solid green;
        padding: 1;
        margin: 1;
        height: auto;
    }

    DataLoadingWidget Button {
        width: 100%;
        margin-top: 1;
    }

    PipelineProgressWidget {
        margin-top: 2;
        padding: 1;
        border: solid cyan;
    }

    PipelineExplanationWidget {
        margin-top: 2;
        padding: 1;
        border: solid blue;
    }

    ConfigurationInfoWidget {
        margin-top: 2;
        padding: 1;
        border: solid yellow;
    }

    #main-panel {
        width: 100%;
        padding: 2;
    }
    """

    TITLE = "Trading System Utilities v1.0"
    SUB_TITLE = "Data preparation and system maintenance"

    BINDINGS = [
        ("q", "quit", "Quit"),
    ]

    def compose(self) -> ComposeResult:
        """Create the UI layout"""
        yield Header()

        with VerticalScroll(id="main-panel"):
            yield DataLoadingWidget()

        yield Footer()

    def action_quit(self):
        """Quit the application"""
        self.exit()

    def action_load_data(self):
        """Load pre-market trading data - runs the full data pipeline"""
        self.notify(
            "🚀 Starting data pipeline...",
            title="Data Pipeline",
            severity="information",
            timeout=3
        )

        # Get reference to widgets
        try:
            progress = self.query_one("#pipeline_progress", PipelineProgressWidget)
        except:
            progress = None

        try:
            config_info = self.query_one("#config_info", ConfigurationInfoWidget)
        except:
            config_info = None

        # Run data loading in background thread to avoid blocking UI
        def run_data_pipeline():
            try:
                # Get symbols from database using centralized function
                db_connection = mysql.connector.connect(
                    host="localhost",
                    port=3306,
                    user="root",
                    password="E_I$S5PFri",
                    database="histFinanData"
                )
                cursor = db_connection.cursor()
                symbols = get_symbols_from_database(cursor)
                cursor.close()
                db_connection.close()

                # Update configuration info with actual symbol count and date
                if config_info and symbols:
                    config_info.symbol_count = len(symbols)
                    if len(symbols) <= 10:
                        config_info.symbol_range = f"{', '.join(symbols)}"
                    else:
                        first_5 = ', '.join(symbols[:5])
                        last_5 = ', '.join(symbols[-5:])
                        config_info.symbol_range = f"{first_5} ... {last_5}"

                # Step 1: Clear day work tables
                try:
                    if progress: progress.step1_status = "running"
                    logger.info("Step 1: Starting to clear day work tables...")
                    clear_day_work_tables()
                    if progress: progress.step1_status = "complete"
                    logger.info("Step 1: Completed successfully")

                    # Update config with table record counts
                    if config_info:
                        config_info._update_table_counts()
                except Exception as e1:
                    if progress:
                        progress.step1_status = "error"
                        progress.step1_error = f"Failed to clear tables: {str(e1)[:100]}"
                    logger.error(f"Step 1 failed: {str(e1)}")
                    raise

                # Step 2: Get historical data
                try:
                    if progress: progress.step2_status = "running"
                    logger.info("Step 2: Starting to download historical data...")

                    # Calculate last 5 business days (1 week)
                    init_date_api, end_date_api, init_date_display, end_date_display = get_last_n_business_days(5)
                    logger.info(f"Step 2: Date range: {init_date_display} to {end_date_display}")

                    if progress:
                        progress.step2_detail = f"[init: {init_date_display}, end: {end_date_display}]"

                    def step2_progress(symbol, count, total):
                        if progress:
                            progress.step2_detail = f"({count}/{total}) [init: {init_date_display}, end: {end_date_display}]"
                        if count % 10 == 0:
                            logger.info(f"Step 2: Processed {count}/{total} symbols")

                    getHistoricalData(init_date=init_date_api, end_date=end_date_api, progress_callback=step2_progress)
                    if progress:
                        progress.step2_status = "complete"
                        progress.step2_detail = f"[init: {init_date_display}, end: {end_date_display}]"
                    logger.info("Step 2: Completed successfully")

                    if config_info:
                        config_info.date_range = f"{init_date_display} to {end_date_display}"
                        config_info._update_table_counts()
                except Exception as e2:
                    if progress:
                        progress.step2_status = "error"
                        error_msg = str(e2)
                        if "date" in error_msg.lower():
                            progress.step2_error = f"Date format error: {error_msg[:80]}"
                        elif "connection" in error_msg.lower() or "timeout" in error_msg.lower():
                            progress.step2_error = f"Network error: Check Polygon.io connection"
                        elif "rate" in error_msg.lower() or "limit" in error_msg.lower():
                            progress.step2_error = f"API rate limit exceeded. Try again later."
                        else:
                            progress.step2_error = f"{error_msg[:120]}"
                    logger.error(f"Step 2 failed: {str(e2)}")
                    raise

                # Step 3: Calculate relative volume
                try:
                    if progress: progress.step3_status = "running"
                    logger.info("Step 3: Starting to calculate relative volume...")

                    def step3_progress(symbol, count, total):
                        if progress:
                            progress.step3_detail = f"({count}/{total})"

                    getRelativeVolumeFactor(progress_callback=step3_progress)
                    if progress:
                        progress.step3_status = "complete"
                        progress.step3_detail = ""
                    logger.info("Step 3: Completed successfully")
                except Exception as e3:
                    if progress:
                        progress.step3_status = "error"
                        progress.step3_error = f"Failed to calculate relative volume: {str(e3)[:100]}"
                    logger.error(f"Step 3 failed: {str(e3)}")
                    raise

                # Refresh Configuration & Results panel with final record counts
                if config_info:
                    config_info._update_table_counts()
                    logger.info("Configuration panel refreshed with final table counts")

                # Success!
                self.notify(
                    "✅ Data pipeline completed successfully!\n   System ready for trading.",
                    title="Data Pipeline",
                    severity="information",
                    timeout=5
                )

            except Exception as e:
                # Enhanced error handling with detailed logging
                import traceback
                error_details = traceback.format_exc()

                # Log detailed error to console
                logger.error(f"Pipeline failed with error: {str(e)}")
                logger.error(f"Full traceback:\n{error_details}")

                # Find which step was running and mark it as error with details
                if progress:
                    for i in range(1, 4):
                        status_var = f"step{i}_status"
                        error_var = f"step{i}_error"
                        if getattr(progress, status_var) == "running":
                            setattr(progress, status_var, "error")

                            # Extract meaningful error message
                            error_msg = str(e)
                            if "date" in error_msg.lower():
                                error_msg = f"Date format error: {error_msg[:100]}"
                            elif "api" in error_msg.lower() or "polygon" in error_msg.lower():
                                error_msg = f"API error: {error_msg[:100]}"
                            elif "database" in error_msg.lower() or "mysql" in error_msg.lower():
                                error_msg = f"Database error: {error_msg[:100]}"
                            elif "permission" in error_msg.lower() or "denied" in error_msg.lower():
                                error_msg = f"Permission error: {error_msg[:100]}"
                            else:
                                error_msg = error_msg[:150] if len(error_msg) > 150 else error_msg

                            setattr(progress, error_var, error_msg)
                            logger.error(f"Step {i} failed: {error_msg}")
                            break

                self.notify(
                    f"❌ Data pipeline failed at Step {i}: {str(e)[:100]}",
                    title="Data Pipeline Error",
                    severity="error",
                    timeout=10
                )

        # Start in background thread
        threading.Thread(target=run_data_pipeline, daemon=True).start()


def main():
    """Run the utilities dashboard"""
    app = UtilsDashboard()
    app.run()


if __name__ == "__main__":
    main()
