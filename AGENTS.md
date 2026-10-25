# Apsor Archive — Agent Guide

Apsor Archive is a local-first, single-owner knowledge and memory archive for files, memories, their lineage, and grounded AI answers. This file is the repository-wide orientation and guardrail sheet; product behavior and API detail belong in the READMEs.

## Purpose

Use this guide to choose the right subsystem, respect cross-cutting invariants, and run the repository gates. Detailed backend rules live in `backend/AGENTS.md`; frontend rules live in `frontend/AGENTS.md`.

## Task orchestration

- The main agent owns the task definition: write a short SSOT plan under `docs/plan/`, create a dedicated worktree and branch, define file ownership, and keep one writer per file set.
- Delegate implementation, QA, and security work to background subagents. Each task must state the worktree, branch, base commit, scope, allowed files, forbidden actions, verification commands, and a no-commit rule.
- QA scripts and screenshots belong under `/tmp`; security reviews are read-only. Subagents must not commit, switch branches, merge, deploy, or touch a live archive database.
- Only the main agent integrates diffs, runs final gates, commits, opens and merges the PR, deploys, and updates local progress notes. Keep the local progress skill current at each milestone.
- `docs/plan/` and `.agents/` are local-only and must not be committed.

## Architecture

- `backend/` is a Python 3.13 FastAPI service. It owns authentication, file and memory ingestion, hybrid retrieval, provider settings, durable ingestion jobs, and the persistent agent. PostgreSQL 17 is the source of truth; Valkey is a disposable cache; original bytes live under the configured data directory.
- `frontend/` is a React 19 + TypeScript + Vite SPA. It uses React Query for server state and a committed Orval client generated from `frontend/openapi.json`. The production build is committed under `frontend/dist`.
- FastAPI serves the SPA and `/api/v1` from the same origin. API routes win before the SPA fallback. The container image copies the committed client; it does not run a frontend build.
- Root deployment files are `Dockerfile`, `docker-compose.yml`, `docker-compose.dev.yml`, `docker-compose.cloudflare-tunnel.yml`, and `docker/caddy/`. The production Compose files run separate API and ingestion-worker services; only the worker drains ingestion jobs.
- `docs/cloudflare-tunnel.md` is the deployment/security guide; `secrets/README.md` documents local secret-file handling. `Makefile` and `start.sh` are the supported local command paths.
- A normal request path is router → service → repository. Cross-cutting resources are created in the app lifespan and exposed through `app.state`; each vertical slice assembles its own dependencies.
- A durable ingestion job and an agent run are separate asynchronous workflows. Neither workflow may hold a request-scoped database session for its full lifetime.

## Key files

- `README.md` — product behavior, feature surface, and operator-facing setup.
- `Makefile` — canonical lint, test, build, API-contract, Compose, and seed commands.
- `backend/AGENTS.md` — backend service rules and verification.
- `frontend/AGENTS.md` — frontend architecture, generated-client, and UI rules.
- `Dockerfile` / `docker-compose*.yml` — production, dev-dependency, and tunnel runtimes.
- `.env.example` / `secrets/README.md` — configuration names and secret-file expectations.

## Conventions

- **Do not hand-edit generated API artifacts.** Backend route/schema changes must regenerate `frontend/openapi.json` and `frontend/src/app/generated-apis-types/` through `make api-export` and `make api-generate`. `make api-check` is the staleness gate. Keep operation IDs stable unless the contract intentionally changes.
- **The committed client is part of the deliverable.** `frontend/dist/` (including `dist/pdfjs/`) is tracked because Docker serves it and never builds it. After frontend changes, rebuild and commit `frontend/dist/`; regenerate and commit the Orval output only when the backend contract changes.
- **Schema changes are migration changes.** Update the SQLAlchemy models, add an Alembic revision, and validate upgrade/downgrade against a development PostgreSQL database. The test suite builds tables from metadata and does not prove a migration is correct.
- **Never commit credentials or archive bytes.** `.env*` (except `.env.example`), `.secrets/`, `secrets/*` (except its README), `backend/data/`, and local archives are ignored. Database-stored provider keys are encrypted at rest and must never be logged, returned in plaintext, or placed in URLs.
- **Keep the validation envelope stable.** Request validation is normalized by the backend to `400 invalid_request`; domain failures use the shared `{status, error, detail}` envelope with stable machine-readable `error` codes.
- **Respect the single-owner boundary.** The supported product is one local owner with one archive; do not introduce tenant or multi-account assumptions without an explicit product change.
- **Archive content is not UI copy.** Frontend UI strings exist in English, Traditional Chinese, and Simplified Chinese; user content, file names, citations, raw URLs, and model output are never translated. Run `bun run i18n:check` after locale changes.
- **Keep tests offline and isolated.** Provider tests use injected fakes. Never call DeepSeek, OpenAI, Tavily, or a live archive database from tests.
- **For documentation-only work, do not start services or run builds merely to validate prose.** Use static checks such as `git diff --check` for docs changes.

## Verification

```bash
# Repository gates (require the documented local dependencies)
make lint
make test
make api-check

# Build the client that Docker will serve
make build
```

`make test` uses the development PostgreSQL and a disposable test database; it must never point at a live archive. For docs-only changes, verify with `git diff --check` and confirm the intended file set with `git status --short`.

## Related guides

- [Backend](./backend/AGENTS.md)
- [Frontend](./frontend/AGENTS.md)
