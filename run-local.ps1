# Windows counterpart of ./start.sh: start the dev database/cache, then serve the API.
#
# Why this exists: psycopg's async mode refuses Windows' default ProactorEventLoop,
# while uvicorn 0.5x picks ProactorEventLoop on win32. We therefore force a
# SelectorEventLoop and tell uvicorn (loop="none") not to replace it.
#
#   .\run-local.ps1              # http://127.0.0.1:8000
#   .\run-local.ps1 -Port 8080
#
# This serves the API only. Uploads stay queued until an ingestion worker runs:
# start one in a second terminal with `cd backend; uv run apsor-archive worker`,
# or set $env:APSOR_INGEST_WORKER_ENABLED = "true" for a single-process dev API.

[CmdletBinding()]
param(
  [string]$HostAddress = "127.0.0.1",
  [int]$Port = 8000
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

if (-not $env:APSOR_DATABASE_URL) {
  if (Get-Command docker -ErrorAction SilentlyContinue) {
    docker compose -f docker-compose.dev.yml up -d --wait
  }
}

if (-not (Test-Path "frontend/dist/index.html")) {
  Write-Warning "frontend/dist is missing. Build it with: cd frontend; bun install; bun run build"
}

Set-Location backend
uv sync

# The app reads ../.secrets/deepseek.env and ../.secrets/openai.env itself.
uv run python -c "import asyncio, uvicorn; asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy()); uvicorn.run('app.main:app', host='$HostAddress', port=$Port, loop='none')"
