#!/bin/bash
# Launcher for Trading System Utilities Dashboard

echo "═══════════════════════════════════════════"
echo "  Trading System Utilities Dashboard"
echo "  Data Preparation & Maintenance"
echo "═══════════════════════════════════════════"
echo ""

# Activate virtual environment
source myenv/bin/activate

# Check if textual is installed
if ! python3 -c "import textual" 2>/dev/null; then
    echo "Installing dependencies..."
    pip install -q textual
fi

echo "Starting utilities dashboard..."
echo "• Load pre-market data"
echo "• System maintenance tools"
echo "• Press 'q' to quit"
echo ""

# Run the utilities dashboard
python3 utils_dashboard.py
