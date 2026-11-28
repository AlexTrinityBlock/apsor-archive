#!/usr/bin/env bash
# Local launcher.
#
#   ./start.sh setup [--defaults] [--dev]   run the setup wizard (writes .env and secrets)
#   ./start.sh [API options]                start dev dependencies, the API, and the
#                                           dedicated ingestion worker
#
# The API and the worker are separate processes, as in production. Stopping
# this script (Ctrl+C) stops both. Set APSOR_START_WORKER=false to run the API
# alone, for example when a worker already runs in another terminal.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

if [[ "${1:-}" == "setup" ]]; then
  shift
  exec "$ROOT/setup.sh" "$@"
fi

if [[ ! -f .env ]]; then
  echo "No .env found. Run ./start.sh setup first (or ./start.sh setup --defaults --dev)." >&2
  echo "Continuing with built-in development defaults." >&2
fi

if [[ -z "${APSOR_DATABASE_URL:-}" ]]; then
  if command -v docker >/dev/null 2>&1; then
    docker compose -f docker-compose.dev.yml up -d --wait
  fi
fi

if [[ ! -f frontend/dist/index.html ]]; then
  echo "frontend/dist is missing. Build it with: cd frontend && bun install && bun run build" >&2
  echo "The API will still start and /docs will work." >&2
fi

cd backend
uv sync

# The app reads .env and .secrets/*.env itself, so nothing is exported here.
# The API never drains ingestion jobs while the dedicated worker runs.
WORKER_PID=""
if [[ "${APSOR_START_WORKER:-true}" == "true" ]]; then
  export APSOR_INGEST_WORKER_ENABLED=false
  uv run apsor-archive worker &
  WORKER_PID=$!
fi

stop_children() {
  if [[ -n "$WORKER_PID" ]] && kill -0 "$WORKER_PID" 2>/dev/null; then
    kill -TERM "$WORKER_PID" 2>/dev/null || true
    wait "$WORKER_PID" 2>/dev/null || true
  fi
}
trap stop_children EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

uv run apsor-archive --host "${APSOR_HOST:-127.0.0.1}" --port "${APSOR_PORT:-8000}" "$@"
