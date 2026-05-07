import yfinance as yf
import pandas as pd
import sqlite3
import mysql.connector
import os
import random
import re
import requests
import time
from bs4 import BeautifulSoup
from datetime import datetime, timedelta, date, timezone
from trading_config import get_symbols_by_price


# ── Hybrid sourcing: Polygon for SO, yfinance for Float/Short/Short% ──
# 2026-05-04 CHANGE: Polygon Short Interest API was returning corrupted
# values for ~5-10% of tickers (VNRX 20×, UP 20×, RAYA 10×, AIRE 25×
# post reverse-split). Cross-checks against stockanalysis.com, Finviz,
# and Yahoo confirmed those values were wrong at the source — not a
# stale-cycle issue. yfinance's `sharesShort` and `shortPercentOfFloat`
# match Yahoo's Key Statistics page exactly (verified live for VNRX,
# AIRE, RAYA, SKYQ — all 4 to the 2nd decimal).
#
# Current sourcing:
#   shares_outstanding   ← Polygon Ticker Overview (SEC filings)
#   float_value          ← yfinance .info["floatShares"]
#   shares_short         ← yfinance .info["sharesShort"]   (was Polygon)
#   short_percent_float  ← yfinance .info["shortPercentOfFloat"]
#                          (precomputed by Yahoo backend, matches the
#                           "Short % of Float" cell on the website)
#
# `polygon_short_interest()` is kept for reference / rollback only —
# no longer called by get_float().
POLYGON_API_KEY = os.environ.get(
    "POLYGON_API_KEY", "0oQUg6UgH34Ala4OF_YYObsT_5Jh2IBJ"
)
POLYGON_BASE = "https://api.polygon.io"
POLYGON_TIMEOUT = 10  # seconds

def get_stocks_in_range(mysql_cursor, float_limit, min_price, max_price):
    mysql_cursor.execute('''
        SELECT ticker, close
        FROM Stocks
        WHERE float_value < %s
        AND close > %s 
        AND close < %s limit 100
    ''', (float_limit, min_price, max_price))

    rows = mysql_cursor.fetchall()

    tickers = [row[0] for row in rows]
    return tickers

def print_current_time():
    current_time = datetime.now()
    
    formatted_time = current_time.strftime("%H:%M:%S:%f")

    return formatted_time[:-3]

def limpio_entero(x):
    # valida: número, convertible a int y > 0
    try:
        v = int(x)
        return v if v > 0 else None
    except (TypeError, ValueError):
        return None

def human_format(num):
    if num is None:
        return "N/A"
    elif num >= 1_000_000_000:
        return f"{num/1_000_000_000:.1f}B"
    elif num >= 1_000_000:
        return f"{num/1_000_000:.1f}M"
    elif num >= 1_000:
        return f"{num/1_000:.1f}K"
    else:
        return str(num)

def query_stock_float_short_interest(symbol):

    conn = sqlite3.connect('histFinanData.db')
    cursor = conn.cursor()    

    query = """
    SELECT float, short_percent_float
    FROM Stocks
    WHERE ticker = ?
    """    

    cursor.execute(query, (symbol, ))

    # Obtener el resultado
    result = cursor.fetchone()

    # Cerrar la conexión
    conn.close()

    if result:
        return {'float': result[0], 'short_percent_float': result[1]}
    else:
        return None    

    # Parameters:
    # max_float: The maximum number of shares outstanding (float) in millions.
    # min_close and max_close: The minimum and maximum closing price range for the stock to be considered.
    # short_percent_float: The percentage of the float that has been sold short.

def get_low_float_stocks(max_float, min_close, max_close, short_percent_float):

    conn = sqlite3.connect('histFinanData.db')
    cursor = conn.cursor()

    query = """
        SELECT * FROM Stocks
        WHERE float < ?
          AND close >= ?
          AND close <= ?
          AND short_percent_float >= ?          
        ORDER BY close ASC
    """
    cursor.execute(query, (max_float, min_close, max_close, short_percent_float))
    rows = cursor.fetchall()

    columns = ["ticker", "close", "stock_index", "avg_month_volume", "shares_outstanding", "float", "shares_short", "short_percent_float"]

    for row in rows:
        stock = dict(zip(columns, row))
        print(
            f"Ticker: {stock['ticker']}\n"
            f"  Close: {stock['close']}\n"
            f"  Shares Outstanding: {human_format(stock['shares_outstanding'])}\n"
            f"  Float: {human_format(stock['float'])}\n"
            f"  Short % Float: {stock['short_percent_float']}\n"
            "--------------------------------------"
        )

    print(f"\nTotal Stocks found: {len(rows)}")

    conn.close()
    result = {row[0]: row[5] for row in rows}
    return result

# ── Polygon helper: fetch weighted_shares_outstanding ──────────────
def polygon_shares_outstanding(symbol):
    """Fetch SO from Polygon Ticker Overview. Returns int or None.
    Uses `weighted_shares_outstanding` (SO assuming all share classes
    converted) — handles multi-class shares correctly, unlike yfinance
    which often only reports Class A."""
    try:
        r = requests.get(
            f"{POLYGON_BASE}/v3/reference/tickers/{symbol}",
            params={"apiKey": POLYGON_API_KEY},
            timeout=POLYGON_TIMEOUT,
        )
        if r.status_code != 200:
            return None
        results = r.json().get("results", {})
        wso = results.get("weighted_shares_outstanding")
        if wso is None or wso <= 0:
            return None
        return int(wso)
    except Exception:
        return None


# ── Polygon helper: fetch most recent short_interest ───────────────
def polygon_short_interest(symbol):
    """Fetch latest short_interest from Polygon Short Interest API.
    Returns int or None. Picks the most recent settlement_date — FINRA
    publishes ~bi-monthly, so this lags real-time by 0-15 days. Same
    cadence Yahoo / Bloomberg / stockanalysis.com use; comes from the
    same upstream FINRA file."""
    try:
        r = requests.get(
            f"{POLYGON_BASE}/stocks/v1/short-interest",
            params={
                "ticker": symbol,
                "sort": "settlement_date.desc",
                "limit": 1,
                "apiKey": POLYGON_API_KEY,
            },
            timeout=POLYGON_TIMEOUT,
        )
        if r.status_code != 200:
            return None
        results = r.json().get("results", [])
        if not results:
            return None
        si = results[0].get("short_interest")
        if si is None or si < 0:
            return None
        return int(si)
    except Exception:
        return None


# ═══════════════════════════════════════════════════════════════════
# get_float() — populates Stocks.shares_outstanding, .float_value,
# .shares_short, .short_percent_float for the price-filtered subset.
#
# 2026-05-04 CHANGE: shares_short + short_percent_float migrated from
# Polygon to yfinance. See module-level comment block at the top for
# the full rationale (Polygon was returning 10×/20×/25× corrupted
# values for a meaningful slice of tickers).
#
# Sanity gates kept as defense-in-depth — yfinance has its own bugs
# (e.g. CMCT float at 1/100th magnitude). Any row violating the math
# invariants (Float > SO, Short > 1.5×SO) gets the offending field
# nulled out, so the dashboard's /low-float scanner never sees
# corrupted ratios.
#
# Original yfinance-only code is preserved at the bottom under
# "LEGACY (pre-2026-05-03)" — comment-only, never executes.
# ═══════════════════════════════════════════════════════════════════

# Sanity-gate threshold: maximum allowed shares_short / shares_outstanding
# ratio. > 1.0 is mathematically possible (naked short selling, multiple
# brokers re-lending the same share), so we don't reject at exactly 1.0.
# The 1.5 threshold allows confirmed real outliers like RDGT
# (Short ≈ SO, ratio ~1.0) but blocks the yfinance bug pattern where
# the ratio is 100× to 100,000×.
SANITY_MAX_SHORT_TO_SO_RATIO = 1.5

# Cross-validation threshold. When yfinance's `shortPercentOfFloat` is
# above this, we additionally scrape stockanalysis.com and Finviz and
# store both as `short_stockanalysis` / `short_finviz` columns. The
# operator can then visually compare the three values to spot yfinance
# bugs (MSAI returned 1.1143 = 111% — clearly bogus when stockanalysis
# says 8.65% and Finviz says 5.80%).
CROSS_VALIDATE_THRESHOLD = 0.05  # 5%

# Polite browser UA — both sites serve different (or no) content to
# bot-looking requests.
SCRAPE_UA = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/120.0.0.0 Safari/537.36"
}
SCRAPE_TIMEOUT = 10  # seconds


def _parse_pct(text):
    """'8.65%' → 0.0865.  '11.04%' → 0.1104.  Anything else → None."""
    if not text:
        return None
    m = re.search(r"([0-9]+\.?[0-9]*)\s*%", text)
    if not m:
        return None
    try:
        return float(m.group(1)) / 100.0
    except ValueError:
        return None


def stockanalysis_short_pct(symbol):
    """Scrape Short % of Float from stockanalysis.com. Returns float
    fraction (0..1) or None on failure / blocked / not present."""
    try:
        r = requests.get(
            f"https://stockanalysis.com/stocks/{symbol.lower()}/statistics/",
            headers=SCRAPE_UA,
            timeout=SCRAPE_TIMEOUT,
        )
        if r.status_code != 200:
            return None
        soup = BeautifulSoup(r.text, "html.parser")
        # Page renders rows as `<tr><td>Short % of Float</td><td>X.XX%</td></tr>`.
        # Match by row text: "Short % of Float" + a "%" value, but exclude
        # the neighbouring "Short % of Shares Outstanding" row.
        for tr in soup.find_all("tr"):
            text = tr.get_text(" | ", strip=True)
            if ("Short % of Float" in text
                    and "%" in text
                    and "Outstanding" not in text):
                return _parse_pct(text)
        return None
    except Exception:
        return None


def finviz_short_pct(symbol):
    """Scrape Short Float from finviz. Returns float fraction or None."""
    try:
        r = requests.get(
            f"https://www.finviz.com/quote.ashx?t={symbol}",
            headers=SCRAPE_UA,
            timeout=SCRAPE_TIMEOUT,
        )
        if r.status_code != 200:
            return None
        soup = BeautifulSoup(r.text, "html.parser")
        # Finviz lays out fundamentals as alternating <td>label</td><td>value</td>.
        cells = soup.find_all("td")
        for i, c in enumerate(cells):
            if c.get_text(strip=True) == "Short Float" and i + 1 < len(cells):
                return _parse_pct(cells[i + 1].get_text(strip=True))
        return None
    except Exception:
        return None


def get_float(progress_callback=None):

    db_connection = mysql.connector.connect(
        host="localhost",
        port=3306,
        user="root",
        password="E_I$S5PFri",
        database="histFinanData"
    )

    mysql_cursor = db_connection.cursor()

    # Wipe ALL short-related columns across the WHOLE Stocks registry
    # before processing. We only refresh the price-filtered subset
    # (~400 tickers); the other ~2,500 rows would otherwise keep
    # whatever stale value was last written — including bogus values
    # from a previous yfinance bug or a different price range.
    #
    # `shares_short` is included because the dashboard's /low-float
    # `Short %` column does:
    #   COALESCE(short_percent_float * 100,
    #            shares_short / float_value * 100)
    # If we only NULL the precomputed value, the fallback still
    # divides a stale shares_short by a stale float and shows
    # absurd ratios (897 %, 799 %, …). Wiping shares_short too makes
    # the fallback return NULL → blank cell. Step 3 refills it per
    # ticker for the price-filtered subset.
    mysql_cursor.execute(
        "UPDATE Stocks SET short_percent_float = NULL, "
        "                  short_finviz = NULL, "
        "                  short_stockanalysis = NULL, "
        "                  shares_short = NULL"
    )
    db_connection.commit()
    print(f"[CLEAR] Wiped short_percent_float / short_finviz / "
          f"short_stockanalysis / shares_short on {mysql_cursor.rowcount} rows.")

    # Float step runs only on the price-filtered subset — fetching float
    # for all 2,947 master tickers would take ~10 minutes via yfinance
    # for symbols we'll never trade. Prices were populated by the
    # previous Last-Price step.
    symbols = get_symbols_by_price(mysql_cursor)
    total = len(symbols)

    print(" ")
    print(f"Retrieved {total} stocks (price-filtered — float is fetched only for tradable subset).")
    print(" ")

    sanity_dropped_float = 0
    sanity_dropped_short = 0

    for i, symbol in enumerate(symbols):

        # Report progress to callback if provided
        if progress_callback:
            progress_callback(symbol, i + 1, total)

        # yfinance still needs polite throttling (it scrapes Yahoo HTML
        # and rate-limits). Polygon is a paid REST API and doesn't.
        if i % 50 == 0:
            radomValue = random.randint(5, 10)
            time.sleep(radomValue)

        # ── 1) Shares Outstanding from Polygon (clean SEC source) ──
        shares_out = polygon_shares_outstanding(symbol)

        # ── 2) Float / Short / Short% from yfinance ────────────────
        # Single yfinance call gives us all three. `shortPercentOfFloat`
        # is Yahoo's precomputed value (e.g. 0.0474 → 4.74%), matching
        # what finance.yahoo.com displays. Storing it lets the dashboard
        # surface the same number Yahoo shows, instead of recomputing
        # it client-side from possibly-corrupted shares_short / SO.
        try:
            info = yf.Ticker(symbol).info
            float_sh    = limpio_entero(info.get("floatShares"))
            sharesShort = limpio_entero(info.get("sharesShort"))
            raw_spf     = info.get("shortPercentOfFloat")
            try:
                shortPercentOfFloat = float(raw_spf) if raw_spf is not None else None
            except (TypeError, ValueError):
                shortPercentOfFloat = None
        except Exception as e:
            print(f"  [WARN] {symbol}: yfinance fetch failed: {e}")
            float_sh = None
            sharesShort = None
            shortPercentOfFloat = None

        # ── Sanity gates (defense-in-depth) ────────────────────────
        # Polygon is much cleaner than yfinance, but we keep the gates
        # in case Polygon ever returns inconsistent values for a ticker
        # (they happen rarely for newly-listed or recently-restructured
        # tickers). Drop values that violate physical invariants.
        if shares_out is not None and float_sh is not None:
            if float_sh > shares_out:
                print(f"  [SANITY] {symbol}: Float {float_sh:,} > SO {shares_out:,} — dropping float (will be NULL)")
                float_sh = None
                sanity_dropped_float += 1

        if shares_out is not None and sharesShort is not None:
            if sharesShort > shares_out * SANITY_MAX_SHORT_TO_SO_RATIO:
                print(f"  [SANITY] {symbol}: Short {sharesShort:,} > {SANITY_MAX_SHORT_TO_SO_RATIO}×SO ({shares_out:,}) — dropping short (will be NULL)")
                sharesShort = None
                sanity_dropped_short += 1

        # ── Cross-validation when yfinance Short% > CROSS_VALIDATE_THRESHOLD ──
        # Scrape stockanalysis.com and Finviz for the same metric so the
        # dashboard's /stocks page can show all three side-by-side and
        # the operator can spot yfinance bugs (e.g. MSAI returning
        # 111.43% when reality is ~8.65%). Below the threshold we don't
        # bother — the extra HTTP cost adds up over 400 tickers.
        sa_pct = None
        fv_pct = None
        if shortPercentOfFloat is not None and shortPercentOfFloat > CROSS_VALIDATE_THRESHOLD:
            sa_pct = stockanalysis_short_pct(symbol)
            fv_pct = finviz_short_pct(symbol)

        spf_pct = f"{shortPercentOfFloat * 100:.2f}%" if shortPercentOfFloat is not None else "None"
        sa_str  = f"{sa_pct * 100:.2f}%" if sa_pct is not None else "—"
        fv_str  = f"{fv_pct * 100:.2f}%" if fv_pct is not None else "—"
        print(f"#{i+1}/{total} - Symbol: {symbol}")
        print(f"  SO (Polygon)         : {shares_out}")
        print(f"  Float (yfinance)     : {float_sh}")
        print(f"  Short (yfinance)     : {sharesShort}")
        print(f"  Short% Float (yfin)  : {spf_pct}")
        if shortPercentOfFloat is not None and shortPercentOfFloat > CROSS_VALIDATE_THRESHOLD:
            print(f"  Short% (stockanal.)  : {sa_str}")
            print(f"  Short% (finviz)      : {fv_str}")
        print(" ")

        if shortPercentOfFloat is not None:
            mysql_cursor.execute("UPDATE Stocks SET short_percent_float = %s WHERE ticker = %s", (shortPercentOfFloat, symbol))

        # Persist cross-validation values regardless of None — None
        # writes a NULL via mysql.connector, which is what we want when
        # the scrape failed or the symbol was below the threshold.
        mysql_cursor.execute("UPDATE Stocks SET short_stockanalysis = %s WHERE ticker = %s", (sa_pct, symbol))
        mysql_cursor.execute("UPDATE Stocks SET short_finviz = %s WHERE ticker = %s", (fv_pct, symbol))

        if sharesShort is not None:
            mysql_cursor.execute("UPDATE Stocks SET shares_short = %s WHERE ticker = %s", (sharesShort, symbol))

        if shares_out is not None:
            mysql_cursor.execute("UPDATE Stocks SET shares_outstanding = %s WHERE ticker = %s", (shares_out, symbol))

        if float_sh is not None:
            mysql_cursor.execute("UPDATE Stocks SET float_value = %s WHERE ticker = %s", (float_sh, symbol))

        # If a value came back None (Polygon failed, yfinance failed,
        # or a sanity gate dropped it), explicitly NULL the column so
        # the dashboard's /low-float scanner stops surfacing any stale
        # value left there by previous runs.
        if float_sh is None:
            mysql_cursor.execute("UPDATE Stocks SET float_value = NULL WHERE ticker = %s", (symbol,))
        if sharesShort is None:
            mysql_cursor.execute("UPDATE Stocks SET shares_short = NULL WHERE ticker = %s", (symbol,))
        if shares_out is None:
            mysql_cursor.execute("UPDATE Stocks SET shares_outstanding = NULL WHERE ticker = %s", (symbol,))
        if shortPercentOfFloat is None:
            mysql_cursor.execute("UPDATE Stocks SET short_percent_float = NULL WHERE ticker = %s", (symbol,))

        db_connection.commit()

    print(" ")
    print(f"[SANITY SUMMARY] Dropped {sanity_dropped_float} broken floats and {sanity_dropped_short} broken shorts during this run.")
    print(" ")

    mysql_cursor.close()
    db_connection.close()


# ═══════════════════════════════════════════════════════════════════
# LEGACY (pre-2026-05-03) — original yfinance-only get_float.
# Preserved for rollback. To revert: rename this to `get_float` and
# remove (or rename) the version above.
# ═══════════════════════════════════════════════════════════════════
#
# def get_float(progress_callback=None):
#
#     db_connection = mysql.connector.connect(
#         host="localhost",
#         port=3306,
#         user="root",
#         password="E_I$S5PFri",
#         database="histFinanData"
#     )
#
#     mysql_cursor = db_connection.cursor()
#
#     symbols = get_symbols_by_price(mysql_cursor)
#     total = len(symbols)
#
#     print(" ")
#     print(f"Retrieved {total} stocks (price-filtered — float is fetched only for tradable subset).")
#     print(" ")
#
#     for i, symbol in enumerate(symbols):
#
#         if progress_callback:
#             progress_callback(symbol, i + 1, total)
#
#         if i % 50 == 0:
#             radomValue = random.randint(5, 10)
#             time.sleep(radomValue)
#
#         ticker = yf.Ticker(symbol)
#         info = ticker.info
#
#         shares_out = limpio_entero(info.get("sharesOutstanding"))
#         float_sh   = limpio_entero(info.get("floatShares"))
#
#         shortPercentOfFloat = info.get("shortPercentOfFloat")
#         sharesShort = limpio_entero(info.get("sharesShort"))
#
#         print(f"#{i+1}/{total} - Symbol: {symbol}")
#         print("Float:", float_sh)
#         print("Short Percent Of Float:", shortPercentOfFloat)
#         print("Shares Short:", sharesShort)
#         print(" ")
#
#         if shortPercentOfFloat is not None:
#             mysql_cursor.execute("UPDATE Stocks SET short_percent_float = %s WHERE ticker = %s", (shortPercentOfFloat, symbol))
#
#         if sharesShort is not None:
#             mysql_cursor.execute("UPDATE Stocks SET shares_short = %s WHERE ticker = %s", (sharesShort, symbol))
#
#         if shares_out is not None:
#             mysql_cursor.execute("UPDATE Stocks SET shares_outstanding = %s WHERE ticker = %s", (shares_out, symbol))
#
#         if float_sh is not None:
#             mysql_cursor.execute("UPDATE Stocks SET float_value = %s WHERE ticker = %s", (float_sh, symbol))
#
#         db_connection.commit()
#
#     mysql_cursor.close()
#     db_connection.close()

    mysql_cursor.close()
    db_connection.close()