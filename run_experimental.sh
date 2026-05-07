#!/bin/bash

# ═══════════════════════════════════════════════════════════════════════════
# Experimental Dashboard Launcher
# ═══════════════════════════════════════════════════════════════════════════
# Independent workspace for testing and experimentation
# Does not interfere with trading dashboard or utils dashboard
# ═══════════════════════════════════════════════════════════════════════════

echo "═══════════════════════════════════════════"
echo "  Experimental Dashboard Launcher"
echo "  🧪 Testing & Experimentation"
echo "═══════════════════════════════════════════"
echo ""
echo "Starting experimental dashboard..."
echo "• Independent from trading and utils dashboards"
echo "• Safe environment for testing new features"
echo "• Press 'q' to quit, 'r' to refresh"
echo ""

# Activate virtual environment
source myenv/bin/activate

# Check if required dependencies are installed
if ! python3 -c "import textual" 2>/dev/null; then
    echo "⚠️  Textual not found. Installing dependencies..."
    pip install textual mysql-connector-python
fi

# Run the experimental dashboard
python3 experimental_dashboard.py
