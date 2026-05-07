#!/usr/bin/env python3
"""
Quick test to verify Polygon.io WebSocket is receiving live trades
Run this during market hours to verify connectivity
"""
from polygon import WebSocketClient
import time

# Test with just a few highly liquid symbols
test_symbols = ["T.AAPL", "T.TSLA", "T.SPY", "T.QQQ", "T.NVDA"]

trade_count = 0
start_time = time.time()

def handle_trade(msgs):
    global trade_count
    for m in msgs:
        trade_count += 1
        elapsed = time.time() - start_time
        print(f"[{elapsed:.1f}s] Trade #{trade_count}: {m.symbol} @ ${m.price} ({m.size} shares)")

        # Stop after 20 trades or 30 seconds
        if trade_count >= 20:
            print("\n✅ SUCCESS: WebSocket is receiving trades!")
            print(f"   Received {trade_count} trades in {elapsed:.1f} seconds")
            exit(0)

def handle_error(ws, error):
    print(f"❌ WebSocket ERROR: {error}")

def handle_close(ws):
    print("🔌 WebSocket connection closed")

print("=" * 60)
print("Polygon.io WebSocket Connection Test")
print("=" * 60)
print(f"Subscribing to: {test_symbols}")
print("Waiting for trades (max 30 seconds)...")
print()

ws = WebSocketClient(
    api_key='hzZItvRA2Rfrri2XEjt2VSyMek9PC1Yu',
    subscriptions=test_symbols,
    error_handler=handle_error,
    close_handler=handle_close
)

try:
    # Run for 30 seconds max
    ws.run(handle_msg=handle_trade)

    # If we get here, connection closed before receiving 20 trades
    elapsed = time.time() - start_time
    if trade_count == 0:
        print(f"\n⚠️  NO TRADES RECEIVED in {elapsed:.1f} seconds")
        print("   Possible reasons:")
        print("   - Market is closed (NYSE/NASDAQ: 9:30 AM - 4:00 PM ET)")
        print("   - Polygon.io API key issue")
        print("   - Network connectivity problem")
    else:
        print(f"\n⚠️  Only {trade_count} trades in {elapsed:.1f} seconds (expected 20+)")
        print("   Market might be in low-volume period")

except KeyboardInterrupt:
    print(f"\n🛑 Stopped by user after {trade_count} trades")
except Exception as e:
    print(f"\n❌ ERROR: {e}")
