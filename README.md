# DendroMatrix

A local-first knowledge and memory archive with a branching file library, a
linear memory timeline, hybrid retrieval, and grounded AI answers.

DendroMatrix is not a note list. It is a retrieval surface designed for a small
number of deliberate tool calls: search a passage, read its neighbours, walk the
path, sample a season, press a new memory, or trace a superseded one. Every
result carries its source, chunk number, and time.

## Why it exists

- **Files have lineage.** A path is a branch, not an overwrite. Re-uploading a
  file grows a new leaf; the previous edition remains addressable as history.
- **Memories are linear and traceable.** A new belief can supersede an old one.
  The old memory leaves the search surface but stays readable through its chain.
- **Search is hybrid.** BM25 over CJK bigrams and Latin tokens runs beside vector
  recall. Results are de-duplicated and fused, with the reason recorded.
- **Time is sampled honestly.** A timeline returns up to five anchors per event
  kind and reports exactly how many events were skipped.
- **AI answers are grounded.** DeepSeek receives retrieved passages, not the
  whole library, and every claim must carry a citation. Without a key, the
  answer endpoint fails closed.
- **Images have their own archive.** A standalone media index turns images into
  captions, OCR text, and visual fingerprints. Text search reaches the captions;
  image search compares visual descriptors. It never mixes with the text chunk
  tree.
- **Documents choose their extractor.** PDFs try text first and fall back to
  vision for scanned pages. DOCX, TXT, JSON, CSV, and logs use text, with AI
  structured metadata; images use vision.
- **The archive is local.** It binds to `127.0.0.1` by default and has no login.
  Run it on your own machine; put it behind Cloudflare Tunnel only if you add
  your own access controls.

## Stack

| Layer | Choice |
|---|---|
| API | Python 3.13, FastAPI, SQLAlchemy 2 async, Alembic, psycopg 3 |
| Storage | PostgreSQL 17 (`pg_trgm` for path fuzzy search) |
| Cache | Valkey / Redis-compatible, with a memory fallback |
| Retrieval | CJK bigram + Latin token n-grams, BM25, signed hashing vectors, RRF |
| AI | DeepSeek `deepseek-flash` (OpenAI-compatible chat completions) |
| Frontend | React 19, TypeScript, Vite, React Router, React Query, Orval |
| Deploy | Docker Compose, optional Cloudflare Tunnel, or bare metal with `uv` |

## Quick start

### Docker Compose (normal)

```bash
docker compose up --build
```

Open <http://127.0.0.1:8000>. The first screen invites you to seed a small demo
archive. The database and file data live on named volumes.

To enable AI answers and AI summaries:

```bash
mkdir -p .secrets
printf 'DENDRO_DEEPSEEK_API_KEY=sk-your-key\n' > .secrets/deepseek.env
chmod 755 .secrets
chmod 644 .secrets/deepseek.env
docker compose up -d --build
```

The Compose file mounts `.secrets/` read-only. The app reads the env file itself,
so the key never becomes a container environment variable and never appears in
`docker compose config`. The `644` mode is required because the API container
runs as a non-root user. The key is gitignored and is never returned by the API.
Without it, summaries fall back to a deterministic extractive form and
`POST /api/v1/ask` returns `503 ai_not_configured`.

### Configure AI in the app

The Settings page is the normal way to configure providers. It writes to the
`ai_provider_config` table:

- **Chat** — DeepSeek or any OpenAI-compatible chat endpoint.
- **Embedding** — offline `hashing`, or `openai` / `openai-compatible`.

The API key is encrypted with Fernet before it is stored. The browser only ever
receives a hint such as `...14f8`; the plaintext key is never returned, logged,
or written to Compose output. `DENDRO_SECRET_KEY` supplies the encryption master
key. If it is unset, a `0600` key file is created at `data/.secret_key` (or
`/data/.secret_key` in Docker), so the encrypted values survive restarts.

Precedence is: **database row → environment → built-in default**. The Settings
page labels each provider with its source. Changing the embedding model does not
rewrite existing vectors; `reindex_required` warns you, and re-ingest a file to
refresh its chunks. Vector search skips chunks whose dimension does not match the
current embedder.

Settings API:

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/v1/settings/ai` | Both provider slots, masked hints, source, reindex advice |
| `PUT` | `/api/v1/settings/ai/{purpose}` | Create/update `chat` or `embedding` |
| `POST` | `/api/v1/settings/ai/{purpose}/test` | One small provider request + latency |
| `DELETE` | `/api/v1/settings/ai/{purpose}/key` | Remove the stored key |
| `POST` | `/api/v1/settings/ai/embedding/reindex` | Re-embed every current chunk with the active provider |

### Local development

```bash
# 1. PostgreSQL + Valkey
docker compose -f docker-compose.dev.yml up -d --wait

# 2. API
cd backend
uv sync
uv run alembic upgrade head
uv run dendromatrix --reload

# 3. Frontend (second terminal)
cd frontend
bun install
bun run dev
```

Vite runs on <http://127.0.0.1:5173> and proxies `/api` to the API. To build the
client that the container serves:

```bash
cd frontend && bun run build
```

`./start.sh` is the shortest bare-metal path: it starts the dev database/cache
if Docker is available, sources `.secrets/deepseek.env`, syncs the backend, and
serves the API and committed client at <http://127.0.0.1:8000>.

### Cloudflare Tunnel

The Cloudflare variant publishes no host port. `cloudflared` connects to a
non-root Caddy reverse proxy, which forwards to the API.

```bash
mkdir -p secrets
# Write the tunnel token; no trailing newline.
printf '%s' 'your-tunnel-token' > secrets/cf_token.txt
chmod 644 secrets/cf_token.txt
export DENDRO_PUBLIC_HOST=archive.example.com
docker compose -f docker-compose.cloudflare.yml up -d --build
```

Point the tunnel ingress for `archive.example.com` at `http://caddy:80`. The
token file is gitignored. See `secrets/README.md` for permissions.

## The six tools

The HTTP API is the tool surface. Each endpoint is deliberately small enough for
an LLM to call in sequence.

| Tool | Endpoint | What it returns |
|---|---|---|
| `search_knowledge` | `GET /api/v1/search?query=&result_number=2` | Top results per source kind from BM25 + vector, fused with RRF and deduplicated |
| `read_file` | `GET /api/v1/files/{id}/chunks/{chunk}?chunk_range=1` | A 1-based chunk window |
| `read_timeline` | `GET /api/v1/timeline?year=&month=&day=&day_range=14` | Up to five sampled events per kind, density, and skip counts |
| `read_path` | `GET /api/v1/paths?path=/history&path_depth=1&fuzzy_search=` | Directories and files, or fuzzy path matches |
| `save_memory` | `POST /api/v1/memories` | A new memory, the deprecated memories it replaced, and any new summary |
| `read_memory` | `GET /api/v1/memories/{id}?memory_range=1&trace_history=true` | Target, neighbours, supersedes, successor, and chain |

Additional surfaces: `POST /api/v1/files` (multimodal intake), `POST
/api/v1/files/text`, `DELETE /api/v1/files/{id}`, `GET /api/v1/tree`,
`POST /api/v1/summaries`, `GET /api/v1/stats`, `GET /api/v1/health`, `GET
/api/v1/ai/status`, and `POST /api/v1/ask`.

Standalone media API:

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/api/v1/media` | Upload an image; vision caption/OCR when configured |
| `GET` | `/api/v1/media` | List current media |
| `GET` | `/api/v1/media/search?query=` | Text → image over caption/OCR/tags |
| `POST` | `/api/v1/media/search/image` | Image → image visual similarity |
| `GET` | `/api/v1/media/{id}/content` | Original image bytes |
| `POST` | `/api/v1/media/{id}/describe` | Re-run AI caption/OCR |
| `DELETE` | `/api/v1/media/{id}` | Soft-delete the media asset |

Document intake (`POST /api/v1/files`) supports:

- **Images** (`jpg`, `jpeg`, `png`, `webp`) — DeepSeek vision caption + OCR.
- **PDF** — pypdf text first; when the text is empty, garbled, or the AI
  structured analysis says `use_vision`, render up to 10 pages with pypdfium2
  and run vision OCR.
- **DOCX** — python-docx paragraphs and tables; embedded images can provide a
  vision fallback.
- **TXT / MD / CSV / JSON / LOG** — direct text plus AI structured metadata
  (title, summary, tags, document_type).

Interactive docs: <http://127.0.0.1:8000/docs>. The OpenAPI schema is the source
for the committed Orval client.

### Generated API client and drift

The repository commits both `frontend/openapi.json` and the generated
`frontend/src/app/generated-apis-types/` client. A fresh clone and the Docker
build therefore work without a running backend. To change the contract:

```bash
cd backend && uv run python -m script.export_openapi
cd ../frontend && bun run api:generate
```

To check that the committed client matches the backend:

```bash
make api-check
```

It re-exports the schema, regenerates the client, and fails on any diff. This
keeps the convenience of a committed client without letting it drift silently.

### Load a real corpus

The Wikipedia loader exercises the same ingestion path as the UI:

```bash
cd backend
uv run python -m script.ingest_wikipedia \
  --lang en --titles Automobile Dendrochronology \
  --prefix /wikipedia/en
```

Ask a question across the imported corpus:

```bash
curl -sS -X POST http://127.0.0.1:8000/api/v1/ask \
  -H 'Content-Type: application/json' \
  -d '{"question":"Who built the first practical automobile?","result_number":5}' | jq
```


## How retrieval works

1. **Normalize** with NFKC and lower-case. Punctuation becomes whitespace.
2. **Index** overlapping CJK bigrams, Latin words, and Latin trigrams. Each chunk
   stores a unique n-gram list with term frequencies.
3. **BM25** scores candidates (`k1=1.2`, `b=0.75`). A union query such as
   `automobile ford` naturally favours chunks that contain both terms.
4. **Vector recall** uses a 384-dimensional signed feature-hashing embedder by
   default, so it works offline. Set `DENDRO_EMBEDDING_PROVIDER=openai` and the
   matching base URL/model to use a hosted embedding model instead.
5. **Fuse** with reciprocal rank fusion. Each source kind keeps its own top
   `result_number`, so a summary cannot be crowded out by file chunks.
6. **Deduplicate** by chunk id, then hydrate the file, memory, or summary row.
7. **Expand on ask.** `/ask` first asks DeepSeek for 2–4 short retrieval queries,
   runs hybrid search for each, and fuses the runs with another RRF pass. This
   finds the passage that answers a full question instead of only the passages
   that repeat its nouns.

If vector recall is unavailable, search still returns BM25 results. If an
embedding call fails during ingestion, the chunk is stored text-only.

### Do I need an embedding model key?

No. The default signed feature-hashing embedder runs offline and gives real
lexical vector recall. BM25 over CJK bigrams handles exact terms and names. If
you want semantic or cross-lingual recall, point the service at an
OpenAI-compatible embedding endpoint:

```bash
mkdir -p .secrets
cat > .secrets/openai.env <<'EOF'
DENDRO_EMBEDDING_PROVIDER=openai
DENDRO_EMBEDDING_BASE_URL=https://api.openai.com/v1
DENDRO_EMBEDDING_MODEL=text-embedding-3-small
DENDRO_EMBEDDING_DIMENSION=1536
DENDRO_EMBEDDING_API_KEY=sk-...
EOF
chmod 755 .secrets
chmod 644 .secrets/openai.env
```

The Settings page can also store this configuration in the database. After
changing the embedding model, open Settings and run **Re-embed library** (or call
`POST /api/v1/settings/ai/embedding/reindex`) so existing chunks get vectors in
the new dimension. Until then, text search still works and vector search skips
the incompatible chunks.

### What is a signed hashing embedder?

It is a deterministic feature-hashing vectorizer, not a trained neural model.
Each token (a CJK bigram, a Latin word, or a Latin trigram) is hashed with
BLAKE2b into one of 384 buckets. One bit of the digest becomes the sign, so
collisions partially cancel instead of always adding up. The bucket values are
accumulated and the vector is L2-normalized.

```text
token -> BLAKE2b -> bucket 0..383 + sign(+1/-1) -> accumulate -> normalize
```

Consequences:

- **No model download, no GPU, no key.** It runs on the CPU in microseconds per
  chunk and needs only a few kilobytes of RAM per vector.
- **Lexical, not semantic.** `car` and `automobile` are different tokens. BM25
  handles exact terms; DeepSeek query expansion supplies related retrieval
  terms for `/ask`.
- **Deterministic.** The same text always produces the same vector, which makes
  ingestion and tests reproducible.
- **Exact scan at personal scale.** The current implementation scans up to
  20,000 current vectors and computes cosine in Python. At a larger corpus,
  replace it with pgvector/HNSW or a hosted embedding model; the
  `EmbedderProtocol` boundary stays the same.


## Data model

The schema follows one rule: source metadata lives in its owning table, and the
unified chunk table stores only the source key.

```text
file ─────────────┐
tree_node ────────┤
memory ───────────┼──> chunk ──> chunk_ngram
memory_summary ───┘
```

- `file`: one row per version. `is_current` and `deleted_at` are soft state;
  ids are never reused.
- `tree_node`: folders and file leaves in one tree; `superseded_by_id` links a
  hidden branch to its replacement.
- `chunk`: `(source_kind, source_id, chunk_index)` with an optional JSONB vector.
- `chunk_ngram`: the inverted index used by BM25.
- `memory`: linear timeline with `supersedes_ids`, `superseded_by_id`, and
  `status=active|deprecated`.
- `memory_summary`: period, source memory ids, themes, generator, and model.
- `ai_provider_config`: one row per purpose (`chat` / `embedding`), with an
  encrypted API key, a safe hint, and the active model/base URL/dimension.
- `media_asset` / `media_ngram`: the standalone visual archive, its OCR/caption
  text, and the n-gram index used for text → image search.

The complete local design notes live under `docs/plan/` (gitignored, Chinese).
The committed code, comments, UI copy, and documentation are English.

## Development checks

```bash
# Backend
cd backend
uv run ruff check .
uv run mypy app
PYTHONUTF8=1 uv run bandit -r app -c pyproject.toml
uv run pip-audit
PYTHONUNBUFFERED=1 uv run pytest -q 2>&1 | tee /tmp/dendromatrix-pytest.log

# Frontend
cd frontend
bun run lint
bun run typecheck
bun run build
bun audit
```

The integration suite uses one real PostgreSQL test database
(`dendromatrix_test`) on the same instance, runs sequentially, and resets every
table between tests. There are exactly ten tests; each one exercises the real
HTTP surface and database.

## Project layout

```text
backend/
  app/
    main.py                     API assembly, lifespan, gzip, SPA mount
    shared/                     error registry and list envelope
    infrastructure/             config, database, cache, embeddings, AI, files
    module/knowledge/
      domain/                   chunking, n-grams, BM25 terms, timeline, summary
      model/                    SQLAlchemy models
      repository/               persistence and retrieval queries
      service/                  orchestration and indexing
      router/                   HTTP adapters
      schema/                   Pydantic contracts
      exception/                stable error codes
    module/media/               standalone image archive and visual retrieval
  alembic/                      migrations
  tests/                        ten integration tests
frontend/
  src/app/
    component/                  shared archive UI
    generated-apis-types/       committed Orval client
    home/ search/ timeline/ library/ tree/ media/ memory/ ask/ ...
  src/apis/fetch-client.ts      the only fetch mutator
  src/lib/                      formatting and safe highlighting
  src/styles/                   paper / night archive tokens
docker-compose.yml              normal deployment
docker-compose.dev.yml          local dependencies
docker-compose.cloudflare.yml   tunnel deployment
docker/caddy/                   non-root reverse proxy for the tunnel
```

## Security and privacy

- No authentication is included. The normal Compose file binds the API to
  `127.0.0.1`; the Cloudflare file publishes no host port.
- Paths reject traversal segments, backslashes, control characters, and
  over-long values. Uploads are capped at 10 MB and restricted to an extension
  allowlist.
- HTML from files and memories is rendered as text through React. The UI never
  uses `dangerouslySetInnerHTML`.
- The DeepSeek key lives in `.secrets/deepseek.env` or the environment. It is
  never logged, returned, or committed. Keys saved from the Settings page are
  encrypted in PostgreSQL and returned only as a four-character hint.
- AI calls happen only for summaries and `POST /ask`. If the provider fails, the
  API returns a stable error instead of inventing an answer.

## License

MIT. See `LICENSE`.
