#!/bin/sh
set -eu

export TRADINGVIEW_FEED_PORT="${TRADINGVIEW_FEED_PORT:-8787}"
export TRADINGVIEW_SYMBOL="${TRADINGVIEW_SYMBOL:-MCX:NATURALGAS1!}"

APP_DIR="$(cd "$(dirname "$0")" && pwd)"
FEED_SCRIPT="${APP_DIR}/live_feed/index.js"

if [ -f "$FEED_SCRIPT" ]; then
  node "$FEED_SCRIPT" &
  NODE_PID=$!
elif [ -f "/app/live_feed/index.js" ]; then
  node /app/live_feed/index.js &
  NODE_PID=$!
else
  echo "Warning: live_feed/index.js not found, skipping background feed bridge"
  NODE_PID=""
fi

cleanup() {
  if [ -n "$NODE_PID" ]; then
    kill "$NODE_PID" 2>/dev/null || true
  fi
}
trap cleanup INT TERM EXIT

exec uvicorn backend.main:app --host 0.0.0.0 --port "${PORT:-8000}"

