#!/usr/bin/env bash
#
# start_trading_day.sh
# ───────────────────────────────────────────────────────────────────
# Daily auto-launcher for the C++ trading system. Designed to be
# triggered by `~/Library/LaunchAgents/com.tan.trader.plist` at
# ~1:45 AM Costa Rica (UTC−6), so the bot is ready before pre-market
# opens at 2:00 AM CR (4:00 AM ET).
#
# Stages (in order — abort on first failure):
#   1. Sync system clock           (./time.sh)
#   2. Pre-market data pipeline    (utils_pipeline.py — clear/last_price/float/historical/rv)
#   3. Bring up IB Gateway         (docker-compose up -d) and wait for it
#   4. Launch the C++ trader       (./trade_receiver --persist)
#
# All output goes to ~/logs/trader_YYYYMMDD.log (one file per launch).
# ───────────────────────────────────────────────────────────────────

set -euo pipefail

# ── Paths ──────────────────────────────────────────────────────────
PROJECT_DIR="/Users/tan/experiments/polygon.io"
VENV_ACTIVATE="${PROJECT_DIR}/myenv/bin/activate"
CPP_DIR="${PROJECT_DIR}/cpp_ultra_low_latency"
LOG_DIR="/Users/tan/logs"

mkdir -p "${LOG_DIR}"
LOG_FILE="${LOG_DIR}/trader_$(date +%Y%m%d).log"

# Redirect EVERYTHING (stdout + stderr) to the daily log file. The
# launchd plist also captures stdout/stderr but this gives us a
# day-stamped, persistent trail outside /tmp.
exec >> "${LOG_FILE}" 2>&1

echo ""
echo "════════════════════════════════════════════════════════════════"
echo "  Trading day start — $(date '+%Y-%m-%d %H:%M:%S %Z')"
echo "════════════════════════════════════════════════════════════════"

cd "${PROJECT_DIR}"

# ── Stage 1 — system clock sync ────────────────────────────────────
# One-shot NTP sync. We don't run ./time.sh because it's an infinite
# loop (sntp every 60 s forever) — appropriate for foreground use,
# wrong for a launcher. macOS already auto-syncs via Apple's NTP, so
# this is mostly belt-and-braces.
#
# `sudo sntp` would prompt for a password and hang under launchd. We
# skip it: macOS keeps the clock close enough on its own. If you want
# stricter sync, add `tan ALL=(ALL) NOPASSWD: /usr/bin/sntp` to sudoers
# and uncomment the line below.
echo "[1/4] Skipping explicit NTP sync (macOS handles it)…"
# sudo -n sntp -sS time.apple.com >/dev/null 2>&1 || true

# ── Stage 2 — pre-market data pipeline ─────────────────────────────
# Python writes Stocks.close, Stocks.float_value, HistoryByMin, and
# RelativeVolumeRatioHour. The C++ trader reads these on startup —
# without fresh data the relative-volume gate is meaningless.
echo "[2/4] Running pre-market data pipeline…"
# shellcheck disable=SC1090
source "${VENV_ACTIVATE}"
python3 utils_pipeline.py

# ── Stage 3 — IB Gateway via Docker ────────────────────────────────
# The C++ trader connects to TWS / IB Gateway on port 7497 (paper) or
# 7496 (live). docker-compose.yml in the project root defines the
# image. `up -d` is idempotent — no-op if the container is already up.
echo "[3/4] Bringing up IB Gateway (docker-compose)…"
docker-compose up -d

# Wait up to 60 s for the gateway port to accept connections. If it
# never opens we still proceed — the C++ trader logs its own connect
# failures, and a restart of just the trader is faster than aborting
# the whole launch.
echo "       Waiting for port 7497…"
for i in {1..30}; do
    if nc -z localhost 7497 2>/dev/null; then
        echo "       OK — port 7497 is open after ${i}× 2 s"
        break
    fi
    sleep 2
done

# ── Stage 4 — launch the C++ trader ────────────────────────────────
echo "[4/4] Starting trade_receiver --persist…"
cd "${CPP_DIR}"

# `exec` replaces this shell with the trader process so launchd
# tracks the actual binary (kill / status work on the real PID).
exec ./trade_receiver --persist
