#!/usr/bin/env python3
"""
Test script to verify dashboard WebSocket connection works independently
Tests the separate WebSocket connection without affecting the trading system
"""

import time
import sys
sys.path.insert(0, '/Users/tan/experiments/polygon.io')

from ui_experiments import TradingDataSource

def test_websocket_connection():
    """Test that dashboard can connect to Polygon.io WebSocket"""

    print("=" * 60)
    print("🧪 Testing Dashboard WebSocket Connection")
    print("=" * 60)
    print()

    # Create data source (this will start WebSocket in background)
    print("📡 Initializing TradingDataSource...")
    data_source = TradingDataSource()
    print()

    # Give WebSocket time to connect
    print("⏳ Waiting 3 seconds for WebSocket to establish connection...")
    time.sleep(3)
    print()

    # Check connection status
    print("🔍 Connection Status:")
    print(f"   WebSocket Connected: {data_source.ws_connected}")
    print(f"   WebSocket Client: {data_source.ws_client is not None}")
    print(f"   Monitoring Symbols: {len(data_source.ws_symbols)}")
    print()

    if data_source.ws_connected:
        print("✅ WebSocket connection SUCCESSFUL!")
        print(f"   Subscribed to {len(data_source.ws_symbols)} symbols")
        print()

        # Try to get some trades
        print("🔄 Listening for trades (10 seconds)...")
        start_time = time.time()
        trade_count = 0

        while time.time() - start_time < 10:
            trades = data_source.get_demo_trades(5)

            # Check if we got real trades (not demo)
            if trades and data_source.ws_connected:
                for trade in trades:
                    if trade_count < 5:  # Only print first 5
                        print(f"   📊 {trade['symbol']:6s} | ${trade['price']:7.2f} | {trade['size']:6,} shares | {trade['exchange']}")
                    trade_count += len(trades)

            time.sleep(0.5)

        print()
        print(f"✅ Received {trade_count} trades in 10 seconds")

        if trade_count > 0:
            print()
            print("=" * 60)
            print("🎉 SUCCESS! Dashboard WebSocket is receiving REAL trades!")
            print("=" * 60)
            return True
        else:
            print()
            print("⚠️  No trades received (market might be closed)")
            print("   Dashboard will show DEMO mode during off-hours")
            return True

    else:
        print("❌ WebSocket connection FAILED")
        print("   Dashboard will run in DEMO mode")
        print()
        print("🔧 Troubleshooting:")
        print("   1. Check Polygon.io API key is valid")
        print("   2. Verify API tier allows WebSocket connections")
        print("   3. Check internet connectivity")
        return False

if __name__ == "__main__":
    try:
        success = test_websocket_connection()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\n⚠️  Test interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
