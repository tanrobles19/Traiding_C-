"""
Trade Analyzer
==============
Analyzes trading signals and order execution to answer questions like:
- Why were buy orders not executed?
- What conditions were not met?
- Timing analysis of signals vs price movements
"""

import mysql.connector
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


def analyze_trading_results():
    """
    Performs comprehensive analysis of trading signals and order execution.

    Returns:
        dict: Analysis results with detailed breakdown
    """

    logger.info("=" * 70)
    logger.info("TRADE ANALYSIS STARTED")
    logger.info("=" * 70)

    # Connect to database
    db_connection = mysql.connector.connect(
        host="localhost",
        port=3306,
        user="root",
        password="E_I$S5PFri",
        database="histFinanData"
    )

    cursor = db_connection.cursor(dictionary=True)

    # ========================================================================
    # 1. ANALYZE TRADE SIGNALS
    # ========================================================================

    cursor.execute("""
        SELECT
            symbol,
            purchasePrediction,
            open,
            close,
            volume,
            relative_volume_hour,
            trade_activity_seconds,
            timestamp_unix,
            high,
            low
        FROM TradeSignalsBuyPerSecond
        ORDER BY timestamp DESC
        LIMIT 100
    """)

    signals = cursor.fetchall()

    # Count by prediction type
    prediction_counts = {}
    buy_signals = []
    non_buy_signals = []

    for signal in signals:
        pred = signal['purchasePrediction']
        prediction_counts[pred] = prediction_counts.get(pred, 0) + 1

        if pred == 'BUY':
            buy_signals.append(signal)
        else:
            non_buy_signals.append(signal)

    # ========================================================================
    # 2. ANALYZE ORDER EXECUTION
    # ========================================================================

    cursor.execute("""
        SELECT
            symbol,
            status,
            open_price,
            ask_price,
            bid_price,
            filledPrice,
            start_timestamp,
            end_timestamp
        FROM Orders
        ORDER BY id DESC
        LIMIT 50
    """)

    orders = cursor.fetchall()

    # Count by status
    order_status_counts = {}
    for order in orders:
        status = order['status']
        order_status_counts[status] = order_status_counts.get(status, 0) + 1

    # ========================================================================
    # 3. ANALYZE RAW TRADES (Price Movement & Timing)
    # ========================================================================

    cursor.execute("""
        SELECT
            symbol,
            MIN(close) as min_price,
            MAX(close) as max_price,
            MIN(timestamp) as first_trade,
            MAX(timestamp) as last_trade,
            SUM(volume) as total_volume,
            COUNT(*) as trade_count
        FROM RawTrades
        WHERE volume >= 100
        GROUP BY symbol
    """)

    trade_stats = cursor.fetchall()

    # ========================================================================
    # 4. DETAILED FAILURE ANALYSIS
    # ========================================================================

    failure_reasons = {}

    for signal in non_buy_signals:
        reason = signal['purchasePrediction']

        if reason not in failure_reasons:
            failure_reasons[reason] = {
                'count': 0,
                'examples': []
            }

        failure_reasons[reason]['count'] += 1

        if len(failure_reasons[reason]['examples']) < 3:
            # Calculate metrics for this signal
            open_price = float(signal['open']) if signal['open'] else 0
            close_price = float(signal['close']) if signal['close'] else 0

            price_change_pct = 0
            if open_price > 0:
                price_change_pct = ((close_price - open_price) / open_price) * 100

            failure_reasons[reason]['examples'].append({
                'symbol': signal['symbol'],
                'open': open_price,
                'close': close_price,
                'price_change': price_change_pct,
                'rv': float(signal['relative_volume_hour']) if signal['relative_volume_hour'] else 0,
                'activity': signal['trade_activity_seconds']
            })

    # ========================================================================
    # 5. TIMING ANALYSIS (RV Threshold vs Risk Limit)
    # ========================================================================

    timing_analysis = []

    for signal in signals[:10]:  # Analyze recent signals
        symbol = signal['symbol']

        # Get the trade that triggered the signal
        cursor.execute("""
            SELECT close, timestamp, volume
            FROM RawTrades
            WHERE symbol = %s
            ORDER BY id ASC
        """, (symbol,))

        trades = cursor.fetchall()

        if not trades:
            continue

        # Calculate when RV threshold was reached
        cumulative_volume = 0
        rv_threshold = float(signal['relative_volume_hour']) if signal['relative_volume_hour'] else 1000
        rv_reached_at = None
        rv_price_at_threshold = None

        for trade in trades:
            if trade['volume'] and int(trade['volume']) >= 100:
                cumulative_volume += int(trade['volume'])

                if cumulative_volume >= rv_threshold and rv_reached_at is None:
                    rv_reached_at = trade['timestamp']
                    rv_price_at_threshold = float(trade['close'])
                    break

        # Calculate risk limit
        open_price = float(signal['open']) if signal['open'] else 0
        risk_limit = open_price * 1.20  # 20% spike risk

        # Find if/when price hit risk limit
        risk_limit_hit = False
        risk_limit_time = None

        for trade in trades:
            if trade['close'] and float(trade['close']) >= risk_limit:
                risk_limit_hit = True
                risk_limit_time = trade['timestamp']
                break

        timing_analysis.append({
            'symbol': symbol,
            'open': open_price,
            'rv_threshold': rv_threshold,
            'rv_reached_at': rv_reached_at,
            'rv_price': rv_price_at_threshold,
            'risk_limit': risk_limit,
            'risk_limit_hit': risk_limit_hit,
            'risk_limit_time': risk_limit_time,
            'prediction': signal['purchasePrediction']
        })

    # ========================================================================
    # COMPILE RESULTS
    # ========================================================================

    cursor.close()
    db_connection.close()

    logger.info("Analysis complete")
    logger.info(f"Total signals: {len(signals)}")
    logger.info(f"BUY signals: {len(buy_signals)}")
    logger.info(f"Non-BUY signals: {len(non_buy_signals)}")

    return {
        'total_signals': len(signals),
        'buy_signals': len(buy_signals),
        'non_buy_signals': len(non_buy_signals),
        'prediction_counts': prediction_counts,
        'order_status_counts': order_status_counts,
        'failure_reasons': failure_reasons,
        'timing_analysis': timing_analysis,
        'trade_stats': trade_stats,
        'recent_signals': signals[:10]
    }


if __name__ == "__main__":
    # For testing
    logging.basicConfig(
        level=logging.INFO,
        format='[%(asctime)s] [ANALYZER] [%(levelname)s] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    result = analyze_trading_results()
    print(f"\nAnalysis complete:")
    print(f"  Total signals: {result['total_signals']}")
    print(f"  BUY signals: {result['buy_signals']}")
    print(f"  Predictions: {result['prediction_counts']}")
