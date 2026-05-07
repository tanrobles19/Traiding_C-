# WebSocket Dashboard

## Overview
Simple real-time trade monitor that displays trades from `multiprocessing_websocket_rv_hour_AI.py` consumer_process.

## Files Created
1. **websocket_dashboard.py** - Textual TUI dashboard with trade table
2. **run_webSocket.sh** - Shell launcher script
3. **WEBSOCKET_DASHBOARD.md** - This documentation

## How It Works

### Data Flow
```
multiprocessing_websocket_rv_hour_AI.py:
  mainT()
    → creates dashboard_queue (line 2789)
    → passes to consumer_process (line 2833)
    → consumer_process sends trades to dashboard_queue (lines 2299-2310)
       ↓
websocket_dashboard.py:
    → receives trades from dashboard_queue
    → displays in real-time table
```

### Integration Points

**In multiprocessing_websocket_rv_hour_AI.py (NO CHANGES MADE):**
- Line 2789: `dashboard_queue = multiprocessing.Queue(maxsize=200)`
- Line 2833: `dashboard_queue` passed as last parameter to `consumer_process`
- Lines 2299-2310: Trades sent to dashboard_queue (inside consumer_process while loop)

**Dashboard receives trade dict:**
```python
{
    'symbol': str,      # Stock symbol
    'price': float,     # Trade price
    'size': int,        # Trade volume
    'timestamp': float, # Unix timestamp (seconds)
    'exchange': str,    # Exchange code
    'conditions': list  # Trade conditions
}
```

## Usage

### Start Dashboard
```bash
./run_webSocket.sh
```

### Features
- **Connect WebSocket Button**: Starts trading system in background (non-blocking mode)
- **Real-Time Trade Table**: Displays last 500 trades with auto-scroll
- **Trade Counter**: Shows total trades received
- **10Hz Refresh Rate**: Updates table 10 times per second for smooth display

### Dashboard Layout
```
╔═══════════════════════════════════════════════════════════════╗
║ WebSocket Trade Monitor                                       ║
╠═══════════════════════════════════════════════════════════════╣
║ Status: ✅ Connected | Trades: 1,234                          ║
║ [Connected]                                                   ║
╠═══════════════════════════════════════════════════════════════╣
║ Real-Time Trades                                              ║
║ ┌────────┬────────┬─────────┬──────┬──────────┐              ║
║ │ Time   │ Symbol │ Price   │ Size │ Exchange │              ║
║ ├────────┼────────┼─────────┼──────┼──────────┤              ║
║ │ 09:30:45 │ AAPL  │ $150.25 │ 100  │ Q        │              ║
║ │ 09:30:44 │ TSLA  │ $245.50 │ 50   │ P        │              ║
║ │ ...                                          │              ║
║ └────────┴────────┴─────────┴──────┴──────────┘              ║
╚═══════════════════════════════════════════════════════════════╝
```

## Technical Details

### Threading Model
1. **Main Thread**: Textual UI event loop
2. **Worker Thread**: Starts trading system (mainT with blocking=False)
3. **Monitor Thread**: Reads from multiprocessing.Queue → local queue.Queue
4. **Timer Callback**: UI updates from local queue at 10Hz

### Queue Architecture
```
consumer_process (trading system)
    ↓ multiprocessing.Queue (maxsize=200)
monitor_thread
    ↓ queue.Queue (maxsize=1000)
update_trades_from_queue (10Hz timer)
    ↓ DataTable widget
```

### Performance
- **Overhead**: ~2μs per trade (queue.put_nowait)
- **Buffer**: 200 trades (multiprocessing) + 1000 trades (local)
- **Display**: Last 500 trades (auto-prune older trades)
- **Drop Strategy**: Silent drop if dashboard can't keep up (no impact on trading)

## Verification

### Test Imports
```bash
source myenv/bin/activate
python3 -c "import websocket_dashboard; print('✅ Dashboard OK')"
python3 -c "import multiprocessing_websocket_rv_hour_AI; print('✅ Trading system OK')"
```

### Check Files
```bash
ls -lh websocket_dashboard.py run_webSocket.sh multiprocessing_websocket_rv_hour_AI.py
```

## Notes

- **No modifications made** to `multiprocessing_websocket_rv_hour_AI.py`
- Dashboard runs independently - no impact on trading system performance
- Trades are sent at line 2299-2310 in consumer_process
- Dashboard connects by calling `mainT(blocking=False)`
- Press Ctrl+C to exit dashboard (trading processes continue in background)

## Dependencies
- textual (auto-installed by run_webSocket.sh)
- Python 3.9+ with myenv virtual environment
- All dependencies from multiprocessing_websocket_rv_hour_AI.py
