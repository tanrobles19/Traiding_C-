#!/usr/bin/env python3
"""
utils_pipeline.py — runs the data-prep pipeline used by the web dashboard.

Five-step pre-market pipeline. Emits one JSON event per line on stdout
so the Next.js dashboard can stream progress as Server-Sent Events.

Step order matters — each step depends on the columns the previous
step populates:

    1. clear        (opt-in)        — wipe day-work tables
    2. last_price                   — Stocks.close for ALL ~2,947 tickers
                                      (Polygon get_last_trade)
    3. float                        — Stocks.float_value for the
                                      price-filtered subset only
                                      (yfinance — slow, hence subset)
    4. historical                   — HistoryByMin for the FULLY filtered
                                      subset (price + float thresholds)
    5. rv                           — RelativeVolumeRatioHour from
                                      HistoryByMin

Events:
    {"type":"start"}
    {"type":"config","min_price":1,"max_price":2,"float_threshold":50000000}
    {"type":"step","step":"<name>","status":"running"|"complete"|"skipped"}
    {"type":"progress","step":"<name>","count":42,"total":637,"symbol":"NVDA"}
    {"type":"step","step":"historical","status":"running","init":"...","end":"..."}
    {"type":"done"}
    {"type":"error","step":"...","message":"..."}

Flags:
    --skip-clear     Skip Step 1 (the destructive table-clear step).
                     Recommended default for the dashboard so we never
                     wipe Orders / TradeSignals / RelativeVolumeRatioHour
                     unless the operator explicitly asks for it.
"""

from __future__ import annotations
import argparse
import json
import sys
import traceback


def emit(**kwargs) -> None:
    """Write one JSON event to stdout, line-buffered."""
    print(json.dumps(kwargs), flush=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-clear",      action="store_true",
                        help="Skip Step 1 (clearing day-work tables).")
    parser.add_argument("--skip-last-price", action="store_true",
                        help="Skip Step 2 (Last price → Stocks.close).")
    parser.add_argument("--skip-float",      action="store_true",
                        help="Skip Step 3 (Float → Stocks.float_value).")
    parser.add_argument("--skip-historical", action="store_true",
                        help="Skip Step 4 (Load historical data).")
    parser.add_argument("--skip-rv",         action="store_true",
                        help="Skip Step 5 (Relative volume).")
    args = parser.parse_args()

    emit(type="start", skip_clear=args.skip_clear)

    # Lazy imports — these touch MySQL / Polygon at module load time, so
    # only import once we've decided we're actually going to run.
    try:
        from utils_dashboard import get_last_n_business_days
        from clean_db import clear_day_work_tables
        from get_previous_close import getPreviousClose
        from get_float import get_float
        from fetch_historycal_data_to_db import getHistoricalData
        from relative_volume_ratio import getRelativeVolumeFactor
        from trading_config import (
            MIN_PRICE_THRESHOLD,
            MAX_PRICE_THRESHOLD,
            FLOAT_THRESHOLD,
        )
    except Exception as e:
        emit(type="error", step="import", message=str(e),
             traceback=traceback.format_exc())
        return 1

    # Surface the symbol-selection thresholds so the dashboard can show
    # "this run is using min_price=X, max_price=Y, float<Z". These come
    # from trading_config.json (loaded by trading_config.py at import),
    # so editing the config in /utils → Save → run pipeline reflects
    # the new values here.
    emit(type="config",
         min_price=MIN_PRICE_THRESHOLD,
         max_price=MAX_PRICE_THRESHOLD,
         float_threshold=FLOAT_THRESHOLD)

    # ── Step 1 ─ Clear day work tables (optional) ────────────────
    if args.skip_clear:
        emit(type="step", step="clear", status="skipped")
    else:
        try:
            emit(type="step", step="clear", status="running")
            clear_day_work_tables()
            emit(type="step", step="clear", status="complete")
        except Exception as e:
            emit(type="error", step="clear", message=str(e),
                 traceback=traceback.format_exc())
            return 1

    # ── Step 2 ─ Last price → Stocks.close (ALL tickers) ─────────
    if args.skip_last_price:
        emit(type="step", step="last_price", status="skipped")
    else:
        try:
            emit(type="step", step="last_price", status="running")

            def step2_cb(symbol, count, total):
                emit(type="progress", step="last_price",
                     symbol=symbol, count=count, total=total)

            getPreviousClose(progress_callback=step2_cb)
            emit(type="step", step="last_price", status="complete")
        except Exception as e:
            emit(type="error", step="last_price", message=str(e),
                 traceback=traceback.format_exc())
            return 1

    # ── Step 3 ─ Float → Stocks.float_value (price-filtered subset) ─
    if args.skip_float:
        emit(type="step", step="float", status="skipped")
    else:
        try:
            emit(type="step", step="float", status="running")

            def step3_cb(symbol, count, total):
                emit(type="progress", step="float",
                     symbol=symbol, count=count, total=total)

            get_float(progress_callback=step3_cb)
            emit(type="step", step="float", status="complete")
        except Exception as e:
            emit(type="error", step="float", message=str(e),
                 traceback=traceback.format_exc())
            return 1

    # ── Step 4 ─ Load historical data → HistoryByMin ─────────────
    if args.skip_historical:
        emit(type="step", step="historical", status="skipped")
    else:
        try:
            from trading_config import HISTORICAL_DAYS
            init_api, end_api, init_disp, end_disp = get_last_n_business_days(HISTORICAL_DAYS)
            emit(type="step", step="historical", status="running",
                 init=init_disp, end=end_disp)

            def step4_cb(symbol, count, total):
                emit(type="progress", step="historical",
                     symbol=symbol, count=count, total=total)

            getHistoricalData(
                init_date=init_api,
                end_date=end_api,
                progress_callback=step4_cb,
            )
            emit(type="step", step="historical", status="complete")
        except Exception as e:
            emit(type="error", step="historical", message=str(e),
                 traceback=traceback.format_exc())
            return 1

    # ── Step 5 ─ Calculate relative volume → RelativeVolumeRatioHour
    if args.skip_rv:
        emit(type="step", step="rv", status="skipped")
    else:
        try:
            emit(type="step", step="rv", status="running")

            def step5_cb(symbol, count, total):
                emit(type="progress", step="rv",
                     symbol=symbol, count=count, total=total)

            getRelativeVolumeFactor(progress_callback=step5_cb)
            emit(type="step", step="rv", status="complete")
        except Exception as e:
            emit(type="error", step="rv", message=str(e),
                 traceback=traceback.format_exc())
            return 1

    emit(type="done")
    return 0


if __name__ == "__main__":
    sys.exit(main())
