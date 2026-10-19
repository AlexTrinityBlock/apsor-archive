SHELL := /bin/bash

.PHONY: help dev-deps api web build test lint up down tunnel seed api-export api-generate api-check

help:
	@printf '%s\n' \
	  'make dev-deps     Start PostgreSQL + Valkey for local development' \
	  'make api          Run the FastAPI server with reload' \
	  'make web          Run the Vite dev server' \
	  'make build        Build the frontend into frontend/dist' \
	  'make test         Run the ten backend integration tests' \
	  'make lint         Run backend and frontend checks' \
	  'make up           Build and start the normal Compose stack' \
	  'make down         Stop the normal Compose stack' \
	  'make tunnel       Build and start the Cloudflare Compose stack' \
	  'make seed         Seed the demo archive through the API' \
	  'make api-export   Export OpenAPI to frontend/openapi.json' \
	  'make api-generate Regenerate the committed Orval client' \
	  'make api-check    Fail if the committed contract/client is stale'

dev-deps:
	docker compose -f docker-compose.dev.yml up -d --wait

api:
	cd backend && uv run dendromatrix --reload

web:
	cd frontend && bun run dev

build:
	cd frontend && bun run build

test:
	cd backend && PYTHONUNBUFFERED=1 uv run pytest -q 2>&1 | tee /tmp/dendromatrix-pytest.log

lint:
	cd backend && uv run ruff check . && uv run mypy app
	cd frontend && bun run lint && bun run typecheck

up:
	docker compose up -d --build

down:
	docker compose down

tunnel:
	docker compose -f docker-compose.cloudflare-tunnel.yml up -d --build

seed:
	curl -sS -X POST http://127.0.0.1:8000/api/v1/demo/seed

api-export:
	cd backend && uv run python -m script.export_openapi

api-generate:
	cd frontend && bun run api:generate

api-check: api-export api-generate
	git diff --exit-code -- frontend/openapi.json frontend/src/app/generated-apis-types
