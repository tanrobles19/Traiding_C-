#!/bin/bash
# Unattended pre-market launch for trade_receiver --persist --IB.
# Fired by ~/Library/LaunchAgents/com.tan.trader.plist at 02:00 CR Mon-Fri.
#
# Steps:
#   1. Make sure Docker Desktop daemon is reachable (start it if not)
#   2. docker-compose up -d (idempotent — no-op if already running)
#   3. Wait for IB Gateway API on 127.0.0.1:4002 (IBC needs ~30-60s after up)
#   4. exec trade_receiver under caffeinate so the Mac cannot sleep mid-run
#
# Logs go to a dated file under logs/trader/. Errors during the bootstrap
# steps are captured BEFORE caffeinate takes over the process.

set -uo pipefail

PROJECT_DIR="/Users/tan/experiments/polygon.io"
TRADER_DIR="$PROJECT_DIR/cpp_ultra_low_latency"
LOG_DIR="$PROJECT_DIR/logs/trader"
DATE_STAMP=$(date +%Y-%m-%d_%H-%M-%S)
LOG_FILE="$LOG_DIR/run_${DATE_STAMP}.log"

mkdir -p "$LOG_DIR"
exec >> "$LOG_FILE" 2>&1

echo "════════════════════════════════════════════════"
echo "[$(date)] start_trader.sh START"
echo "════════════════════════════════════════════════"

# Already-running guard. launchd should not double-fire, but if the
# operator manually launched a session and it's still alive, refuse
# to start a second one (would race for IB clientId 0 + the same
# Polygon connection slot).
if pgrep -x trade_receiver >/dev/null; then
    echo "[$(date)] ⚠ trade_receiver already running (pid $(pgrep -x trade_receiver)) — abort"
    exit 0
fi

# 1. Docker Desktop must be reachable. Start it if not — open -a is
#    a no-op when Docker.app is already running.
if ! /usr/local/bin/docker info >/dev/null 2>&1; then
    echo "[$(date)] Docker daemon not reachable — launching Docker Desktop"
    open -a Docker
    for i in $(seq 1 30); do
        if /usr/local/bin/docker info >/dev/null 2>&1; then break; fi
        sleep 3
    done
    if ! /usr/local/bin/docker info >/dev/null 2>&1; then
        echo "[$(date)] ❌ Docker daemon never came up after 90s — abort"
        exit 1
    fi
fi
echo "[$(date)] ✅ Docker daemon reachable"

# 2. Bring up IB Gateway container (idempotent).
cd "$PROJECT_DIR"
/usr/local/bin/docker-compose up -d
echo "[$(date)] docker-compose up -d issued"

# 3. Wait for the API listener inside the container. `docker ps` reports
#    "Up" before IBC has finished login, so we poll the port directly.
echo "[$(date)] Waiting for IB Gateway port 4002…"
for i in $(seq 1 60); do
    if /usr/bin/nc -z 127.0.0.1 4002 2>/dev/null; then
        echo "[$(date)] ✅ Port 4002 listening (after $((i*2))s)"
        break
    fi
    sleep 2
done
if ! /usr/bin/nc -z 127.0.0.1 4002 2>/dev/null; then
    echo "[$(date)] ❌ Port 4002 never opened in 120s — abort"
    exit 1
fi

# Extra grace for IBC to clear post-login dialogs ("Login Messages",
# data subscription notices, etc.). The C++ preflight handshake will
# exercise auth right after this.
sleep 10

# 4. Hand control to the trader, wrapped in caffeinate so the Mac
#    cannot enter idle/disk/system sleep while it runs. The display
#    is allowed to stay off (no -d). exec replaces this shell — when
#    trade_receiver exits, caffeinate exits, and so does this script.
cd "$TRADER_DIR"
echo "[$(date)] Launching: caffeinate -ims ./trade_receiver --persist --IB"
exec /usr/bin/caffeinate -ims ./trade_receiver --persist --IB
