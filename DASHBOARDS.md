# Trading System Dashboards

This project has three independent dashboards, each serving a different purpose.

---

## 1. 📊 Real-Time Trading Dashboard
**File**: `ui_experiments.py`
**Launcher**: `./run_dashboard.sh`

**Purpose**: Monitor live trading operations with real-time WebSocket data

**Features**:
- Live WebSocket trade data from Polygon.io
- Real-time position tracking from Interactive Brokers
- Trade signals monitoring
- Recent orders display
- System health metrics
- Manual trading interface (Buy Stock button)

**Use Case**: Day-to-day trading operations and monitoring

---

## 2. 🛠️ Utilities Dashboard
**File**: `utils_dashboard.py`
**Launcher**: `./run_utils.sh`

**Purpose**: Data preparation and maintenance tasks

**Features**:
- Pre-market data pipeline execution
- Progress tracking for each data loading step:
  - Clear day tables
  - Get previous close prices
  - Retrieve float data
  - Load historical data
  - Calculate relative volume ratios

**Use Case**: Pre-market data preparation (run before market opens)

---

## 3. 🧪 Experimental Dashboard
**File**: `experimental_dashboard.py`
**Launcher**: `./run_experimental.sh`

**Purpose**: Testing and experimentation workspace

**Features**:
- Three customizable experiment widgets
- Sample data display widget
- Interactive input/button testing widget
- Counter demonstration widget
- Independent data source
- Safe environment for testing new features

**Use Case**: Development, testing, and prototyping new features

**Key Bindings**:
- `q` - Quit
- `r` - Refresh

---

## Quick Start

```bash
# Run trading dashboard
./run_dashboard.sh

# Run utilities dashboard
./run_utils.sh

# Run experimental dashboard
./run_experimental.sh
```

---

## Dashboard Independence

Each dashboard is **completely independent**:
- ✅ Separate Python files
- ✅ Separate launcher scripts
- ✅ Can run simultaneously without conflicts
- ✅ No shared state between dashboards
- ✅ Modifications to one don't affect others

---

## Customization Guide

### Experimental Dashboard

The experimental dashboard is designed to be easily customized:

1. **Add new widgets**: Create new classes inheriting from `Static`
2. **Modify data source**: Update `ExperimentalDataSource` class
3. **Change layout**: Edit the `compose()` method
4. **Add key bindings**: Update the `BINDINGS` list
5. **Customize CSS**: Modify the `CSS` string

**Example - Add a new widget**:
```python
class ExperimentWidget4(Static):
    """Your new widget"""

    def compose(self) -> ComposeResult:
        yield Label("[bold blue]My New Widget[/bold blue]")
        # Add your components here
```

Then add to layout:
```python
def compose(self) -> ComposeResult:
    # ... existing code ...
    yield ExperimentWidget4()
```

---

## Architecture Notes

- **Trading Dashboard**: Connected to live trading system processes
- **Utils Dashboard**: Standalone, executes data pipelines
- **Experimental Dashboard**: Standalone, queries database directly
