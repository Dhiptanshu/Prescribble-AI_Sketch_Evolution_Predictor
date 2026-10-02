#!/usr/bin/env bash
# One-command launcher for Ubuntu/Linux/macOS: starts the local server and opens the browser.
cd "$(dirname "$0")" || exit 1
PORT="${1:-8765}"
URL="http://localhost:${PORT}"
PY="$(command -v python3 || command -v python)"
if [ -z "$PY" ]; then echo "Python 3 not found. Install it with: sudo apt install python3"; exit 1; fi
( sleep 1; (xdg-open "$URL" || open "$URL" || echo "Open $URL in your browser") >/dev/null 2>&1 ) &
exec "$PY" serve.py "$PORT"
