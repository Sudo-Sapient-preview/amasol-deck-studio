#!/usr/bin/env bash
# Start amasol Deck Studio: builds the web app if needed, then serves API + UI on HOST:PORT.
set -euo pipefail
cd "$(dirname "$0")"
HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-4300}"

if [ ! -x skill/.venv/bin/python ]; then
  (cd skill && bash scripts/setup.sh)
fi
if [ ! -x server/.venv/bin/python ]; then
  python3 -m venv server/.venv
  server/.venv/bin/pip install -q -r server/requirements.txt
fi
if [ ! -f web/dist/index.html ] || [ -n "$(find web/src web/index.html -newer web/dist/index.html 2>/dev/null | head -1)" ]; then
  (cd web && { [ -d node_modules ] || npm install; } && npm run build)
fi
cd server
exec .venv/bin/uvicorn app.main:app --host "$HOST" --port "$PORT" --timeout-graceful-shutdown 5
