#!/bin/bash
# Starts Solo's server + an ngrok tunnel, keeps the Mac awake while it runs,
# and prints the current public link. Ctrl+C stops everything cleanly.
set -e
cd "$(dirname "$0")"

if [ ! -x ./.bin/ngrok ]; then
  echo "ngrok not found at ./.bin/ngrok - set it up first (see AGENTS.md)."
  exit 1
fi

PIDS=()
cleanup() {
  echo ""
  echo "Stopping..."
  for pid in "${PIDS[@]}"; do
    kill "$pid" 2>/dev/null || true
  done
}
trap cleanup EXIT INT TERM

echo "Keeping this Mac awake while the demo runs (caffeinate)..."
caffeinate -dims &
PIDS+=($!)

echo "Starting the app server..."
./.venv/bin/uvicorn app.main:app --port 8000 > /tmp/solo_server.log 2>&1 &
PIDS+=($!)

echo "Starting ngrok..."
./.bin/ngrok http 8000 --log=stdout > /tmp/solo_ngrok.log 2>&1 &
PIDS+=($!)

echo "Waiting for the server..."
until curl -sf http://localhost:8000/api/practice >/dev/null 2>&1; do sleep 0.5; done

echo "Waiting for the ngrok tunnel..."
until curl -sf http://127.0.0.1:4040/api/tunnels 2>/dev/null | grep -q "public_url"; do sleep 0.5; done

URL=$(curl -s http://127.0.0.1:4040/api/tunnels \
  | ./.venv/bin/python -c "import json,sys; d=json.load(sys.stdin); print(next(t['public_url'] for t in d['tunnels'] if t['public_url'].startswith('https://')))")

echo ""
echo "Solo is live:"
echo "  Dashboard:    $URL"
echo "  Booking page: $URL/book"
echo ""
echo "The QR code on the Practice setup tab always reflects this tunnel automatically."
echo "Press Ctrl+C to stop the server, ngrok, and release the Mac to sleep normally."
echo ""

wait
