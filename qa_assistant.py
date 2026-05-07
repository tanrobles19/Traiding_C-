"""
Q&A Assistant for Trading System
=================================
Analyzes database and code to answer user questions about trading signals and orders.
"""

import mysql.connector
import logging
from datetime import datetime
from typing import Dict, Any

logger = logging.getLogger(__name__)


class TradingQAAssistant:
    """Smart Q&A assistant that answers trading-related questions"""

    def __init__(self):
        self.db_config = {
            "host": "localhost",
            "port": 3306,
            "user": "root",
            "password": "E_I$S5PFri",
            "database": "histFinanData"
        }

    def _get_connection(self):
        """Get database connection"""
        return mysql.connector.connect(**self.db_config)

    def ask(self, question: str) -> str:
        """
        Process user question and return answer.

        Args:
            question: User's question string

        Returns:
            Formatted answer string with Rich markup
        """
        question_lower = question.lower()

        # Route to appropriate handler based on keywords
        if "no signal" in question_lower or "not created" in question_lower and "signal" in question_lower:
            return self._why_no_signals()

        elif "no buy" in question_lower or "no order" in question_lower:
            return self._why_no_buy_orders()

        elif "relative volume" in question_lower or "rv" in question_lower:
            return self._explain_relative_volume()

        elif "signal" in question_lower and ("breakdown" in question_lower or "show" in question_lower):
            return self._show_signal_breakdown()

        elif "check rv" in question_lower or "rv data" in question_lower:
            return self._check_rv_data()

        elif "failed" in question_lower or "failure" in question_lower:
            return self._show_failure_reasons()

        elif "help" in question_lower or "what can" in question_lower:
            return self._show_help()

        else:
            return self._default_response(question)

    def _why_no_signals(self) -> str:
        """Analyze why signals weren't generated"""
        try:
            conn = self._get_connection()
            cursor = conn.cursor(dictionary=True)

            # Check if RawTrades has data
            cursor.execute("SELECT COUNT(*) as count FROM RawTrades")
            trades_count = cursor.fetchone()['count']

            if trades_count == 0:
                return "[bold red]❌ No trades in RawTrades table[/bold red]\n\nYou need to download trades first using the '📥 Download Trades' button."

            # Check unique symbols in RawTrades
            cursor.execute("SELECT COUNT(DISTINCT symbol) as count FROM RawTrades")
            symbols_count = cursor.fetchone()['count']

            # Check if any signals were generated
            cursor.execute("SELECT COUNT(*) as count FROM TradeSignalsBuyPerSecond WHERE temp_action = 'simulation'")
            signals_count = cursor.fetchone()['count']

            cursor.close()
            conn.close()

            # Build response
            response = "[bold cyan]🔍 Signal Generation Analysis[/bold cyan]\n\n"
            response += f"[white]RawTrades:[/white] {trades_count:,} trades from {symbols_count} symbols\n"
            response += f"[white]Signals Generated:[/white] {signals_count}\n\n"

            if signals_count == 0:
                response += "[bold yellow]⚠️ No signals generated[/bold yellow]\n\n"
                response += "[white]Possible reasons:[/white]\n"
                response += "1. Relative volume threshold not met (need RV >= 0.5)\n"
                response += "2. Price increase from open < 2%\n"
                response += "3. Low trading activity (< 40% of seconds with trades)\n"
                response += "4. Not enough volume accumulated\n\n"
                response += "[cyan]Tip:[/cyan] Check trading_system.log for [DEBUG] lines showing RV factor from dashboard"

            else:
                response += f"[bold green]✅ {signals_count} signals generated successfully![/bold green]\n"
                response += "\nUse: [cyan]'show signal breakdown'[/cyan] to see details"

            return response

        except Exception as e:
            logger.error(f"Error in _why_no_signals: {e}", exc_info=True)
            return f"[bold red]Error:[/bold red] {str(e)}"

    def _why_no_buy_orders(self) -> str:
        """Analyze why buy orders weren't created"""
        try:
            conn = self._get_connection()
            cursor = conn.cursor(dictionary=True)

            # Check signals
            cursor.execute("""
                SELECT COUNT(*) as count, purchasePrediction
                FROM TradeSignalsBuyPerSecond
                WHERE temp_action = 'simulation'
                GROUP BY purchasePrediction
            """)
            signal_breakdown = cursor.fetchall()

            # Check orders
            cursor.execute("SELECT COUNT(*) as count FROM Orders")
            order_count = cursor.fetchone()['count']

            cursor.close()
            conn.close()

            response = "[bold cyan]🔍 Buy Order Analysis[/bold cyan]\n\n"

            if not signal_breakdown:
                response += "[yellow]No signals found in database.[/yellow]\n"
                response += "Run the simulation first using '▶️ Run Simulation' button."
                return response

            buy_signals = sum(s['count'] for s in signal_breakdown if s['purchasePrediction'] == 'BUY')
            total_signals = sum(s['count'] for s in signal_breakdown)

            response += f"[white]Total Signals:[/white] {total_signals}\n"
            response += f"[green]BUY Signals:[/green] {buy_signals}\n"
            response += f"[white]Orders Created:[/white] {order_count}\n\n"

            if buy_signals == 0:
                response += "[bold red]⚠️ No BUY signals generated[/bold red]\n\n"
                response += "[white]Signal breakdown:[/white]\n"
                for s in signal_breakdown:
                    response += f"  • {s['purchasePrediction']}: {s['count']}\n"

                response += "\n[yellow]Common reasons for non-BUY:[/yellow]\n"
                response += "  1. Price increase < 2% from open\n"
                response += "  2. Low trading activity (< 40% of elapsed seconds)\n"
                response += "  3. Doji candle (close = open)\n"
            else:
                response += f"[green]✅ {buy_signals} BUY signals generated![/green]\n"
                if order_count == 0:
                    response += "\n[yellow]Note:[/yellow] Simulation doesn't place actual orders.\n"
                    response += "The main trading system (multiprocessing_websocket_rv_hour.py) handles order execution."

            return response

        except Exception as e:
            logger.error(f"Error in _why_no_buy_orders: {e}", exc_info=True)
            return f"[bold red]Error:[/bold red] {str(e)}"

    def _explain_relative_volume(self) -> str:
        """Explain relative volume calculation"""
        from trading_config import RELATIVE_VOLUME_FACTOR

        response = "[bold cyan]📊 Relative Volume Explained[/bold cyan]\n\n"
        response += "[white]What is Relative Volume (RV)?[/white]\n"
        response += "RV compares current volume to historical average volume for the same hour.\n\n"

        response += "[white]Formula:[/white]\n"
        response += "  RV = (Cumulative Volume) / (Hourly Average Volume)\n\n"

        response += "[white]Example:[/white]\n"
        response += "  If a stock normally trades 10,000 shares in the 9 AM hour,\n"
        response += "  and it's already traded 5,000 shares by 9:30 AM,\n"
        response += "  then RV = 5,000 / 10,000 = 0.5x (half the hourly average)\n\n"

        response += f"[white]Current Threshold:[/white] [yellow]{RELATIVE_VOLUME_FACTOR}x[/yellow]\n"
        response += f"Signals trigger when RV >= {RELATIVE_VOLUME_FACTOR}x\n\n"

        response += "[white]Data Source:[/white]\n"
        response += "  • Historical data: RelativeVolumeRatioHour table\n"
        response += "  • Real-time volume: Accumulated from RawTrades\n\n"

        response += "[cyan]Why it matters:[/cyan]\n"
        response += "High relative volume indicates unusual trading activity,\n"
        response += "which often precedes significant price movements."

        return response

    def _show_signal_breakdown(self) -> str:
        """Show breakdown of all generated signals"""
        try:
            conn = self._get_connection()
            cursor = conn.cursor(dictionary=True)

            cursor.execute("""
                SELECT
                    purchasePrediction,
                    COUNT(*) as count,
                    AVG(relative_volume_hour) as avg_rv,
                    AVG((close - open) / open * 100) as avg_price_change
                FROM TradeSignalsBuyPerSecond
                WHERE temp_action = 'simulation'
                GROUP BY purchasePrediction
                ORDER BY count DESC
            """)

            breakdown = cursor.fetchall()
            cursor.close()
            conn.close()

            if not breakdown:
                return "[yellow]No signals found. Run simulation first.[/yellow]"

            response = "[bold cyan]📊 Signal Breakdown[/bold cyan]\n\n"
            total = sum(s['count'] for s in breakdown)
            response += f"[white]Total Signals:[/white] {total}\n\n"

            for s in breakdown:
                pct = (s['count'] / total * 100) if total > 0 else 0
                color = "green" if s['purchasePrediction'] == 'BUY' else "yellow"

                response += f"[{color}]{s['purchasePrediction']}:[/{color}] {s['count']} ({pct:.1f}%)\n"
                response += f"  Avg RV: {s['avg_rv']:.2f}x\n"
                response += f"  Avg Price Change: {s['avg_price_change']:.2f}%\n\n"

            return response

        except Exception as e:
            logger.error(f"Error in _show_signal_breakdown: {e}", exc_info=True)
            return f"[bold red]Error:[/bold red] {str(e)}"

    def _check_rv_data(self) -> str:
        """Check RelativeVolumeRatioHour table status"""
        try:
            conn = self._get_connection()
            cursor = conn.cursor(dictionary=True)

            # Get total count
            cursor.execute("SELECT COUNT(*) as count FROM RelativeVolumeRatioHour")
            total_count = cursor.fetchone()['count']

            # Get symbol count
            cursor.execute("SELECT COUNT(DISTINCT symbol) as count FROM RelativeVolumeRatioHour")
            symbol_count = cursor.fetchone()['count']

            # Get sample data
            cursor.execute("""
                SELECT symbol, hour, amPm, relative_volume
                FROM RelativeVolumeRatioHour
                LIMIT 5
            """)
            samples = cursor.fetchall()

            cursor.close()
            conn.close()

            response = "[bold cyan]📊 Relative Volume Data Status[/bold cyan]\n\n"
            response += f"[white]Total Entries:[/white] {total_count:,}\n"
            response += f"[white]Unique Symbols:[/white] {symbol_count}\n\n"

            if total_count == 0:
                response += "[bold red]⚠️ Table is EMPTY![/bold red]\n\n"
                response += "[yellow]Action Required:[/yellow]\n"
                response += "Run: ./run_data_processing.sh\n"
                response += "This will populate historical volume data."
            else:
                response += "[green]✅ Data loaded successfully[/green]\n\n"
                response += "[white]Sample entries:[/white]\n"
                for s in samples:
                    response += f"  {s['symbol']}: {s['hour']}:00 {s['amPm']} → {s['relative_volume']:,.0f} shares/hour\n"

            return response

        except Exception as e:
            logger.error(f"Error in _check_rv_data: {e}", exc_info=True)
            return f"[bold red]Error:[/bold red] {str(e)}"

    def _show_failure_reasons(self) -> str:
        """Show top failure reasons for non-BUY signals"""
        try:
            conn = self._get_connection()
            cursor = conn.cursor(dictionary=True)

            cursor.execute("""
                SELECT
                    symbol,
                    purchasePrediction,
                    open,
                    close,
                    volume,
                    relative_volume_hour,
                    trade_activity_seconds
                FROM TradeSignalsBuyPerSecond
                WHERE temp_action = 'simulation'
                  AND purchasePrediction != 'BUY'
                ORDER BY timestamp DESC
                LIMIT 10
            """)

            failures = cursor.fetchall()
            cursor.close()
            conn.close()

            if not failures:
                return "[yellow]No failed signals found.[/yellow]"

            response = "[bold cyan]🔍 Top Signal Failures[/bold cyan]\n\n"

            for f in failures:
                price_change = ((f['close'] - f['open']) / f['open'] * 100) if f['open'] > 0 else 0

                response += f"[white]{f['symbol']}:[/white] {f['purchasePrediction']}\n"
                response += f"  Price: ${f['open']:.2f} → ${f['close']:.2f} ({price_change:+.2f}%)\n"
                response += f"  Volume: {f['volume']:,} | RV: {f['relative_volume_hour']:.2f}x\n"
                response += f"  Activity: {f['trade_activity_seconds']} seconds\n\n"

            return response

        except Exception as e:
            logger.error(f"Error in _show_failure_reasons: {e}", exc_info=True)
            return f"[bold red]Error:[/bold red] {str(e)}"

    def _show_help(self) -> str:
        """Show available commands"""
        response = "[bold cyan]🤖 Q&A Assistant Help[/bold cyan]\n\n"
        response += "[white]Available Questions:[/white]\n\n"

        response += "[yellow]Signal Analysis:[/yellow]\n"
        response += "  • Why no signals?\n"
        response += "  • Show signal breakdown\n"
        response += "  • Show failed signals\n\n"

        response += "[yellow]Order Analysis:[/yellow]\n"
        response += "  • Why no buy orders?\n\n"

        response += "[yellow]System Info:[/yellow]\n"
        response += "  • What is relative volume?\n"
        response += "  • Check RV data\n\n"

        response += "[cyan]Tip:[/cyan] Type questions naturally - keywords are detected automatically!"

        return response

    def _default_response(self, question: str) -> str:
        """Default response for unrecognized questions"""
        response = "[yellow]🤔 I'm not sure how to answer that.[/yellow]\n\n"
        response += "Try asking:\n"
        response += "  • Why no signals?\n"
        response += "  • Why no buy orders?\n"
        response += "  • What is relative volume?\n"
        response += "  • Show signal breakdown\n"
        response += "  • Help\n\n"
        response += f"[dim]Your question: {question}[/dim]"

        return response
