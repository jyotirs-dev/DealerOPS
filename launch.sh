#!/usr/bin/env bash
# Launch DealerOPS: Flask backend (port 5001) + Vite frontend (port 5173).
# Usage: ./launch.sh          -> dev mode (both servers, hot reload)
#        ./launch.sh --prod   -> build frontend, serve everything from Flask on 5001
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

PYTHON="$ROOT/.venv/bin/python"
if [[ ! -x "$PYTHON" ]]; then
  echo "Creating virtualenv and installing Python dependencies..."
  python3 -m venv .venv
  "$PYTHON" -m pip install -q -r requirements.txt
fi

if [[ ! -d frontend/node_modules ]]; then
  echo "Installing frontend dependencies..."
  (cd frontend && npm install)
fi

export HOST="${HOST:-127.0.0.1}"
export PORT="${PORT:-5001}"

if [[ "${1:-}" == "--prod" ]]; then
  echo "Building frontend..."
  (cd frontend && npm run build)
  export FLASK_DEBUG=0
  echo "Serving app at http://$HOST:$PORT"
  exec "$PYTHON" app.py
fi

export FLASK_DEBUG="${FLASK_DEBUG:-1}"

cleanup() { kill "${BACKEND_PID:-}" "${FRONTEND_PID:-}" 2>/dev/null || true; }
trap cleanup EXIT INT TERM

"$PYTHON" app.py &
BACKEND_PID=$!

(cd frontend && npm run dev) &
FRONTEND_PID=$!

echo
echo "Backend:  http://$HOST:$PORT"
echo "Frontend: http://localhost:5173   (Ctrl+C stops both)"
echo
wait
