# Contributing

Apsor Archive is a self-hosted, single-deployment archive. Contributions are
welcome as issues and pull requests. Read `AGENTS.md`, `backend/AGENTS.md`, and
`frontend/AGENTS.md` before changing architecture; they describe the slice
boundaries and invariants that reviews check.

## Prerequisites

- Python 3.13 with `uv`; `backend/pyproject.toml` requires 3.13 or newer.
- Bun 1.3.6, the version pinned in `frontend/package.json`.
- Docker Engine or Docker Desktop with Compose v2 (`docker compose`).
- Git. GNU Make is optional; every target below has a direct command.

The dev stack provides PostgreSQL 17 on `127.0.0.1:55432` (role `apsor`,
database `apsor_archive`) and Valkey 8 on `127.0.0.1:56379`. The API listens on
`127.0.0.1:8000`; Vite on `127.0.0.1:5173`, proxying `/api`.

## Local setup

From a fresh clone:

```bash
git clone https://github.com/AlexTrinityBlock/apsor-archive.git
cd apsor-archive
docker compose -f docker-compose.dev.yml up -d --wait
cd backend
uv sync && uv run alembic upgrade head
uv run apsor-archive --reload
```

```bash
# second terminal
cd apsor-archive/frontend
bun install
bun run dev
```

Open <http://127.0.0.1:5173>. The first visit asks you to create the root
account. The app runs without an AI key; AI features need a provider key as
described in `.env.example` and `secrets/README.md`.

```bash
# equivalent Make targets
make dev-deps   # docker compose -f docker-compose.dev.yml up -d --wait
make api        # cd backend && uv run apsor-archive --reload
make web        # cd frontend && bun run dev
```

`make api` and `make web` do not install dependencies or migrate the database;
run `uv sync`, `uv run alembic upgrade head`, and `bun install` once first.

## Required checks before a pull request

Run these from the repository root with the development dependencies up.

- `make lint` runs `ruff check .` and `mypy app` in `backend/`, then
  `bun run lint`, `bun run typecheck`, and `bun run i18n:check` in `frontend/`.
- `make test` runs the backend integration suite against the disposable
  `apsor_archive_test` database, rebuilt with Alembic; never use a live archive.
- `make api-check` exports OpenAPI, regenerates the Orval client, and fails if
  `frontend/openapi.json` or `frontend/src/app/generated-apis-types/` differs.
- `make build` is required when frontend sources change. Rebuild and commit
  `frontend/dist/` (including `dist/pdfjs/`); the container serves it.

Without `make`:

```bash
(cd backend && uv run ruff check . && uv run mypy app)
(cd frontend && bun run lint && bun run typecheck && bun run i18n:check)
(cd backend && PYTHONUNBUFFERED=1 uv run pytest -q)
(cd frontend && bun run build)
(cd backend && uv run python -m script.export_openapi)
(cd frontend && bun run api:generate)
git diff --exit-code -- frontend/openapi.json frontend/src/app/generated-apis-types
```

## API contract rules

FastAPI routes and schemas are the source of truth. `make api-export` writes
`frontend/openapi.json`; `make api-generate` writes the Orval client.

- Never hand-edit either artifact. After a route, request, response, or status
  change, run `make api-export` and `make api-generate` and commit the results.
- Keep `operation_id` values stable unless the contract change is deliberate.
- `make api-check` is the staleness gate.

## Database schema rules

A model change needs an Alembic revision under `backend/alembic/versions/` and
a verified upgrade and downgrade against a development PostgreSQL database:

```bash
(cd backend && uv run alembic upgrade head)
(cd backend && uv run alembic downgrade -1)
(cd backend && uv run alembic upgrade head)
```

Private tables carry `user_id`, use composite `(id, user_id)` foreign keys,
have an RLS policy, and grant the required privileges to `apsor_app`. Add the
table to `backend/tests/conftest.py`. Global config tables use
read-all/root-write policies. The suite runs migrations, not `create_all`; it
does not replace the downgrade check.

## Localisation

Interface strings exist in English, Traditional Chinese, and Simplified
Chinese. Add every key to all three locales under
`frontend/src/app/i18n/locales/`. Never translate user content, file names,
citations, raw URLs, or model output. Run `bun run i18n:check` after locale
changes; `make lint` also runs it.

## Commits and pull requests

The history uses Conventional Commits-style `type(scope): subject`, for
example `feat(library): add inline rename and Lucide action icons`. The scope
is optional for repository-wide changes; subjects are short, imperative,
start lowercase, and have no trailing period.

Send one logical change per pull request. In the description, state what
changed, why, and what you verified: the checks you ran, any migration or API
contract change, and deployment or security implications. Commit generated
artifacts only when their sources changed. Never commit credentials, filled-in
`.env` files, `.secrets/`, archive bytes, or local databases.

## Security

Read [SECURITY.md](SECURITY.md) before reporting a security issue. Do not
report vulnerabilities in a public issue or pull request; use GitHub's private
vulnerability reporting. Keep tests offline with injected provider fakes.
