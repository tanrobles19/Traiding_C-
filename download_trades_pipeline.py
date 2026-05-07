#!/usr/bin/env python3
"""
download_trades_pipeline.py — downloads ALL trades AND quotes for a
given (symbol, year, month, day, hour, minute) from Polygon.io and
stores them into the MySQL `RawTrades` and `RawQuotes` tables.

Originally this pipeline only handled trades. Extended 2026-05-05
so a single dashboard click pulls both feeds in the same minute
window, enabling the bid/ask-aware strategies in the next-step
bucket of cpp_ultra_low_latency/CLAUDE.md (#14 OBI, #15 spread,
#17 top-of-book erosion, #18 tape aggressiveness — all of which
need historical quotes to backtest before Q.* WebSocket lands).

Emits one JSON event per stdout line so the Next.js dashboard can
stream progress over SSE.

Events:
    {"type":"start","symbol":"PHGE","minute":"2026-01-26 15:10"}
    {"type":"step","step":"download_trades","status":"running"}
    {"type":"progress","step":"download_trades","count":42}
    {"type":"step","step":"download_trades","status":"complete","count":1234}
    {"type":"step","step":"save_trades","status":"running"}
    {"type":"progress","step":"save_trades","count":500,"total":1234}
    {"type":"step","step":"save_trades","status":"complete","count":1234}
    {"type":"step","step":"download_quotes","status":"running"}
    {"type":"progress","step":"download_quotes","count":1000}
    {"type":"step","step":"download_quotes","status":"complete","count":58430}
    {"type":"step","step":"save_quotes","status":"running"}
    {"type":"progress","step":"save_quotes","count":10000,"total":58430}
    {"type":"step","step":"save_quotes","status":"complete","count":58430}
    {"type":"done","trades_saved":1234,"quotes_saved":58430}
    {"type":"error","step":"...","message":"...","traceback":"..."}
"""
from __future__ import annotations

import argparse
import json
import sys
import traceback
from datetime import datetime, timezone

import pytz
import mysql.connector
from polygon import RESTClient


POLYGON_API_KEY = "0oQUg6UgH34Ala4OF_YYObsT_5Jh2IBJ"

MYSQL_CONFIG = {
    "host":     "localhost",
    "port":     3306,
    "user":     "root",
    "password": "E_I$S5PFri",
    "database": "histFinanData",
}


def emit(**kwargs) -> None:
    print(json.dumps(kwargs), flush=True)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--year",   type=int, required=True)
    p.add_argument("--month",  type=int, required=True)
    p.add_argument("--day",    type=int, required=True)
    p.add_argument("--hour",   type=int, required=True)
    p.add_argument("--minute", type=int, required=True)
    p.add_argument("--symbol", type=str, required=True)
    args = p.parse_args()

    symbol = args.symbol.strip().upper()
    minute_label = f"{args.year:04d}-{args.month:02d}-{args.day:02d} {args.hour:02d}:{args.minute:02d}"

    emit(type="start", symbol=symbol, minute=minute_label)

    client = RESTClient(POLYGON_API_KEY)
    dt = datetime(args.year, args.month, args.day, args.hour, args.minute, 0)
    start_ns = int(dt.timestamp() * 1_000_000_000)
    end_ns = start_ns + 60_000_000_000  # +60 seconds
    cr_tz = pytz.timezone("America/Costa_Rica")

    # ── Step 1: download trades ──────────────────────────────────────
    aggregates = []
    try:
        emit(type="step", step="download_trades", status="running")

        for t in client.list_trades(
            ticker=symbol,
            timestamp_gte=start_ns,
            timestamp_lte=end_ns,
            order="asc",
            limit=50000,
            sort="timestamp",
        ):
            ns_ts = t.participant_timestamp
            dt_utc = datetime.fromtimestamp(ns_ts / 1e9, tz=timezone.utc)
            dt_local = dt_utc.astimezone(cr_tz)

            aggregates.append({
                "price":          t.price,
                "size":           t.size,
                "timestamp":      dt_local,
                "unix_timestamp": ns_ts,
                "conditions":     t.conditions,
                "trade_id":       t.id,
                "exchange":       t.exchange,
                "trf_id":         t.trf_id,
            })

            n = len(aggregates)
            if n % 50 == 0 or n == 1:
                emit(type="progress", step="download_trades", count=n)

        emit(type="step", step="download_trades", status="complete", count=len(aggregates))
    except Exception as e:
        emit(type="error", step="download_trades", message=str(e),
             traceback=traceback.format_exc())
        return 1

    # ── Step 2: save trades to MySQL `RawTrades` ─────────────────────
    trades_saved = 0
    if aggregates:
        try:
            emit(type="step", step="save_trades", status="running")

            conn = mysql.connector.connect(**MYSQL_CONFIG)
            cur = conn.cursor()

            total = len(aggregates)

            for row in aggregates:
                conds = row.get("conditions") or []
                conditions_str = ", ".join(map(str, conds)) if conds else "None"

                ts = row["timestamp"]
                timestamp_str = ts.isoformat()

                exchange = row.get("exchange")
                if exchange in (None, ""):
                    exchange = "N/A"

                cur.execute(
                    """
                    INSERT INTO RawTrades
                      (symbol, close, volume, date, hour, minute, second, amPm,
                       transactions, timestamp, conditions, trade_id, exchange, trf_id)
                    VALUES
                      (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        symbol,
                        row["price"],
                        row["size"],
                        "N/A",
                        "00",
                        "00",
                        ts.second,
                        "AM",
                        row["unix_timestamp"],
                        timestamp_str,
                        conditions_str,
                        row.get("trade_id"),
                        exchange,
                        row.get("trf_id"),
                    ),
                )
                trades_saved += 1

                if trades_saved % 100 == 0 or trades_saved == total:
                    emit(type="progress", step="save_trades",
                         count=trades_saved, total=total)

            conn.commit()
            cur.close()
            conn.close()

            emit(type="step", step="save_trades", status="complete", count=trades_saved)
        except Exception as e:
            emit(type="error", step="save_trades", message=str(e),
                 traceback=traceback.format_exc())
            return 1
    else:
        emit(type="step", step="save_trades", status="skipped")

    # ── Step 3: download quotes ──────────────────────────────────────
    # Quotes (NBBO snapshots) are 10-50× denser than trades — a busy
    # minute can produce tens of thousands of rows. Polygon's
    # `list_quotes` mirrors `list_trades` but returns bid/ask pairs.
    quotes = []
    try:
        emit(type="step", step="download_quotes", status="running")

        for q in client.list_quotes(
            ticker=symbol,
            timestamp_gte=start_ns,
            timestamp_lte=end_ns,
            order="asc",
            limit=50000,
            sort="timestamp",
        ):
            ns_ts = q.participant_timestamp or q.sip_timestamp
            dt_utc = datetime.fromtimestamp(ns_ts / 1e9, tz=timezone.utc)
            dt_local = dt_utc.astimezone(cr_tz)

            bid = q.bid_price
            ask = q.ask_price
            spread = (ask - bid) if (bid is not None and ask is not None) else None

            quotes.append({
                "bid_price":       bid,
                "bid_size":        q.bid_size,
                "bid_exchange":    q.bid_exchange,
                "ask_price":       ask,
                "ask_size":        q.ask_size,
                "ask_exchange":    q.ask_exchange,
                "spread":          spread,
                "timestamp":       dt_local,
                "unix_timestamp":  ns_ts,
                "sequence_number": q.sequence_number,
                "conditions":      q.conditions,
                "indicators":      q.indicators,
                "tape":            q.tape,
            })

            n = len(quotes)
            if n % 500 == 0 or n == 1:
                emit(type="progress", step="download_quotes", count=n)

        emit(type="step", step="download_quotes", status="complete", count=len(quotes))
    except Exception as e:
        emit(type="error", step="download_quotes", message=str(e),
             traceback=traceback.format_exc())
        # Don't return — trades are already saved successfully.
        emit(type="done", trades_saved=trades_saved, quotes_saved=0)
        return 1

    # ── Step 4: save quotes to MySQL `RawQuotes` ─────────────────────
    quotes_saved = 0
    if quotes:
        try:
            emit(type="step", step="save_quotes", status="running")

            conn = mysql.connector.connect(**MYSQL_CONFIG)
            cur = conn.cursor()

            total = len(quotes)

            for row in quotes:
                conds = row.get("conditions") or []
                conditions_str = ", ".join(map(str, conds)) if conds else "None"

                inds = row.get("indicators") or []
                indicators_str = ", ".join(map(str, inds)) if inds else "None"

                ts = row["timestamp"]
                timestamp_str = ts.isoformat()

                bid_ex = row.get("bid_exchange")
                if bid_ex in (None, ""):
                    bid_ex = "N/A"
                ask_ex = row.get("ask_exchange")
                if ask_ex in (None, ""):
                    ask_ex = "N/A"

                cur.execute(
                    """
                    INSERT INTO RawQuotes
                      (symbol, bid_price, bid_size, bid_exchange,
                       ask_price, ask_size, ask_exchange, spread,
                       timestamp, unix_timestamp, sequence_number,
                       conditions, indicators, tape)
                    VALUES
                      (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        symbol,
                        row["bid_price"],
                        row["bid_size"],
                        bid_ex,
                        row["ask_price"],
                        row["ask_size"],
                        ask_ex,
                        row["spread"],
                        timestamp_str,
                        row["unix_timestamp"],
                        row.get("sequence_number"),
                        conditions_str,
                        indicators_str,
                        row.get("tape"),
                    ),
                )
                quotes_saved += 1

                if quotes_saved % 1000 == 0 or quotes_saved == total:
                    emit(type="progress", step="save_quotes",
                         count=quotes_saved, total=total)

            conn.commit()
            cur.close()
            conn.close()

            emit(type="step", step="save_quotes", status="complete", count=quotes_saved)
        except Exception as e:
            emit(type="error", step="save_quotes", message=str(e),
                 traceback=traceback.format_exc())
            emit(type="done", trades_saved=trades_saved, quotes_saved=quotes_saved)
            return 1
    else:
        emit(type="step", step="save_quotes", status="skipped")

    emit(type="done", trades_saved=trades_saved, quotes_saved=quotes_saved)
    return 0


if __name__ == "__main__":
    sys.exit(main())
