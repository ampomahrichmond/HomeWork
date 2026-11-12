#!/usr/bin/env bash
# Start the Retention Schedule Determination Engine on http://localhost:8050
set -e
cd "$(dirname "$0")"
if [ ! -d .venv ]; then
  python3 -m venv .venv
  ./.venv/bin/pip install -q --upgrade pip
  ./.venv/bin/pip install -q -r requirements.txt
fi
[ -f .env ] && set -a && . ./.env && set +a
echo "Open http://localhost:${PORT:-8050}"
exec ./.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port "${PORT:-8050}"
