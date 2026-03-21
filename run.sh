#!/bin/bash
# ──────────────────────────────────────
# OpenHer Backend · Quick Start
# Usage: ./run.sh          (foreground, see logs)
#        ./run.sh --bg     (background, logs → .data/server.log)
#        PORT=9000 ./run.sh (custom port)
# ──────────────────────────────────────

set -e
cd "$(dirname "$0")"

PORT=${PORT:-8000}
LOG_FILE=".data/server.log"

# Activate venv
if [ -d ".venv" ]; then
    source .venv/bin/activate
fi

# Kill existing process on the port
PID=$(lsof -ti:$PORT 2>/dev/null || true)
if [ -n "$PID" ]; then
    kill $PID 2>/dev/null
    echo "♻️  Killed process $PID on port $PORT"
    sleep 1
fi

if [ "$1" = "--bg" ]; then
    mkdir -p "$(dirname "$LOG_FILE")"
    echo "🚀 Starting OpenHer backend on port $PORT (background)"
    echo "   Logs → $LOG_FILE"
    echo "   Stop → kill \$(lsof -ti:$PORT)"
    nohup uvicorn main:app --host 0.0.0.0 --port $PORT > "$LOG_FILE" 2>&1 &
    sleep 2
    if lsof -ti:$PORT > /dev/null 2>&1; then
        echo "✅ Backend running (PID $!)"
    else
        echo "❌ Failed to start, check $LOG_FILE"
        exit 1
    fi
else
    echo "🚀 Starting OpenHer backend on port $PORT..."
    echo "   Press Ctrl+C to stop"
    echo ""
    uvicorn main:app --host 0.0.0.0 --port $PORT
fi
