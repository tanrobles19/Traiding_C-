"""
Trading System Configuration
=============================
Centralized configuration for symbol selection and trading parameters.
This ensures all processes (data loading, WebSocket, dashboard) use the SAME symbols.

Symbol-selection thresholds (min_price, max_price, float_threshold)
are loaded from `trading_config.json` at module import — that file is
the single source of truth shared with the C++ trader and the Next.js
dashboard's /utils config panel. Hardcoded values below are fallback
defaults used only if the JSON is missing or malformed.
"""

import json
from pathlib import Path


def _load_trading_config_json() -> dict:
    """Load `trading_config.json` from this file's directory. Returns
    {} on any error (file missing, malformed JSON, IO failure)."""
    p = Path(__file__).resolve().parent / "trading_config.json"
    try:
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


_JSON = _load_trading_config_json()

# ============================================================================
# Symbol Selection Criteria (MUST match Trading Configuration panel)
# ============================================================================

# Price range for symbol filtering — JSON wins so the dashboard's
# /utils edits (which write trading_config.json via /api/config) take
# effect on the next pipeline run, no Python restart required.
MIN_PRICE_THRESHOLD = _JSON.get("min_price",       1)   # Minimum stock price
MAX_PRICE_THRESHOLD = _JSON.get("max_price",       5)   # Maximum stock price

# Float thresholds
FLOAT_THRESHOLD = _JSON.get("float_threshold", 50000000)  # Maximum float (50M shares - momentum strategy)
LOW_FLOAT_THRESHOLD = 10000000  # Low float threshold (7M shares)

# Number of business days to download in Step 4 (historical data → HistoryByMin).
# Configurable via /utils Trading Configuration panel. Default 5.
HISTORICAL_DAYS = _JSON.get("historical_days", 5)

# Volume and signal thresholds
RELATIVE_VOLUME_THRESHOLD = 2               # 5x relative volume for standard stocks
RELATIVE_VOLUME_THRESHOLD_LOW_FLOAT = 3     # 3x relative volume for low float stocks
INCREASE_FROM_OPEN = 1                      # 2% minimum price increase
PRICE_SPIKE_RISK_THRESHOLD = 20             # 20% maximum spike from open

# Trading parameters
TRADE_CAPITAL = 500                    # $300 per trade
MAX_LOSS_TOLERANCE_PER_TRADE = 0.95    # 10% max loss (stop at 90% of entry)
TRADE_SIGNAL_LIMIT = 20                # Max signals per symbol per session

# Short interest
SHORT_INTEREST_RATIO = 0.05            # 5% minimum short interest

# ============================================================================
# Simulation Configuration
# ============================================================================

# Relative volume threshold
RELATIVE_VOLUME_FACTOR = 1         # 0.5x hourly avg volume to trigger

# Stop-loss configuration
MAX_LOSS_TOLERANCE_PER_TRADE = 0.91    # 10% max loss (90% of entry price)

# Price increase threshold
INCREASE_FROM_OPEN = 3                 # 2% minimum price increase

# Signal limits
TRADE_SIGNAL_LIMIT = 20                # Max signals per symbol per session

# Activity threshold
ACTIVITY_PERCENTAGE = 0.01             # % activity threshold

# Simulation settings
SIMULATOR_CONSUMER_ID = 99             # Simulator ID
SIMULATOR_PORT = 7497                  # Paper trading port
STALE_THRESHOLD_MINUTES = 10           # Stale threshold in minutes


def get_symbol_selection_query():
    """
    Returns the standardized SQL query for symbol selection.
    ALL data loading processes MUST use this query.

    Returns:
        tuple: (query_string, parameters_tuple)
    """
    query = """
        SELECT ticker, close
        FROM Stocks
        WHERE float_value < %s
          AND close >= %s
          AND close <= %s
        ORDER BY ticker ASC
    """
    params = (FLOAT_THRESHOLD, MIN_PRICE_THRESHOLD, MAX_PRICE_THRESHOLD)

    return query, params


def get_symbols_from_database(mysql_cursor):
    """
    Get the list of symbols using the standardized criteria.
    ALL processes should call this function.

    Args:
        mysql_cursor: MySQL cursor object

    Returns:
        list: List of ticker symbols
    """
    query, params = get_symbol_selection_query()
    mysql_cursor.execute(query, params)
    rows = mysql_cursor.fetchall()

    tickers = [row[0] for row in rows]
    return tickers


def get_all_symbols(mysql_cursor):
    """
    Every ticker in the Stocks master registry — no filter applied.

    Used by the pipeline's Last-Price step: we cannot filter by price
    yet because that step is exactly what populates `Stocks.close`.
    Returns the full ~2,947-row registry.
    """
    mysql_cursor.execute("SELECT ticker FROM Stocks ORDER BY ticker ASC")
    return [row[0] for row in mysql_cursor.fetchall()]


def get_symbols_by_price(mysql_cursor):
    """
    Tickers within the configured price range, IGNORING float_value.

    Used by the pipeline's Float step: prices are populated (Step 2
    just ran) but floats are not yet — so filtering by `float_value`
    would either drop everything (default 0) or use stale data. Price
    alone is the right gate here so we fetch float only for the
    tickers we'll actually trade.
    """
    query = """
        SELECT ticker FROM Stocks
        WHERE close >= %s AND close <= %s
        ORDER BY ticker ASC
    """
    mysql_cursor.execute(query, (MIN_PRICE_THRESHOLD, MAX_PRICE_THRESHOLD))
    return [row[0] for row in mysql_cursor.fetchall()]


# ============================================================================
# Display configuration summary
# ============================================================================

def print_config():
    """Print configuration summary for verification"""
    print("=" * 60)
    print("TRADING SYSTEM CONFIGURATION")
    print("=" * 60)
    print(f"Price Range: ${MIN_PRICE_THRESHOLD:.2f} - ${MAX_PRICE_THRESHOLD:.2f}")
    print(f"Float Threshold: {FLOAT_THRESHOLD:,} shares")
    print(f"Low Float Threshold: {LOW_FLOAT_THRESHOLD:,} shares")
    print(f"Relative Volume: {RELATIVE_VOLUME_THRESHOLD}x")
    print(f"Relative Volume (Low Float): {RELATIVE_VOLUME_THRESHOLD_LOW_FLOAT}x")
    print(f"Capital per Trade: ${TRADE_CAPITAL}")
    print("=" * 60)
