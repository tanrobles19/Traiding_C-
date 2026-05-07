#!/bin/bash
# Quick launcher for the trading system dashboard

echo "═══════════════════════════════════════════"
echo "  Trading System Dashboard Launcher"
echo "  🟢 LIVE WebSocket Edition"
echo "═══════════════════════════════════════════"
echo ""

# Activate virtual environment
source myenv/bin/activate

# Check if textual is installed
if ! python3 -c "import textual" 2>/dev/null; then
    echo "Installing dependencies..."
    pip install -q textual
fi

echo "Starting dashboard with LIVE WebSocket feed..."
echo "• Separate WebSocket connection (zero trading impact)"
echo "• Real-time trade data from Polygon.io"
echo "• Press Ctrl+C to exit"
echo ""

# Run the dashboard
python3 ui_experiments.py
