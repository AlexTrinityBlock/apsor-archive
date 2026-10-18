#!/usr/bin/env bash
# Local launcher: starts the dev database/cache if needed, then serves the API.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

if [[ -f .secrets/deepseek.env ]]; then
  # shellcheck disable=SC1091
  set -a
  source .secrets/deepseek.env
  set +a
fi

if [[ -z "${DENDRO_DATABASE_URL:-}" ]]; then
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
exec uv run dendromatrix --host "${DENDRO_HOST:-127.0.0.1}" --port "${DENDRO_PORT:-8000}" "$@"
