# Deploy Apsor Archive with Cloudflare Tunnel

This guide deploys the complete Apsor Archive stack on a Docker host and exposes
it through a Cloudflare Tunnel. The origin publishes **no inbound port**:
`cloudflared` makes outbound connections to Cloudflare, and Cloudflare reaches
the local Caddy reverse proxy over that tunnel.

This is the **Cloudflare Tunnel** deployment. A future pure Cloudflare
Serverless deployment is a separate architecture and must use its own
configuration file; do not mix the two.

## Architecture

```text
Browser
  │  HTTPS
  ▼
Cloudflare edge (DNS, TLS, optional Access/WAF)
  │  Tunnel
  ▼
cloudflared ──► Caddy :80 ──► API :8000
                               │
                               ├── PostgreSQL 17
                               ├── Valkey
                               └── host ./data-cloudflare (bound to /data)
                                      ▲
                               worker process
```

Compose services:

| Service | Role |
|---|---|
| `db` | PostgreSQL 17 with a persistent named volume |
| `cache` | Valkey, used for the optional cache |
| `api` | FastAPI, serves the API and committed SPA build; originals live in `./data-cloudflare` |
| `worker` | Dedicated durable-ingestion worker sharing the same host directory |
| `caddy` | Non-root reverse proxy, port 80 inside the Compose network only |
| `cloudflare-tunnel` | `cloudflared` connector with the tunnel token |

The Compose project is `apsor-archive-cloudflare`. The API lifespan worker is
disabled in this stack. The separate `worker` service owns the ingestion queue,
so exactly one process drains jobs.

## Prerequisites

- A domain managed by Cloudflare.
- A Docker host with Docker Engine and the Compose plugin.
- Outbound HTTPS/QUIC access from the host. No router port forwarding or
  public IP is required.
- A Cloudflare tunnel token.
- A host data directory owned by the container uid:
  `mkdir -p data-cloudflare && sudo chown -R 10001:10001 data-cloudflare`.
- At least 2 GB of RAM for the database, API, worker, Caddy, and connector.
  The stack is designed for a single owner and a single host.

## 1. Create the tunnel

In the Cloudflare dashboard:

1. Open **Zero Trust → Networks → Tunnels**.
2. Select **Create a tunnel**.
3. Choose **Cloudflared** as the connector.
4. Name the tunnel, for example `apsor-archive-home`.
5. Copy the tunnel token. Treat it as a secret.
6. Add a public hostname:
   - **Subdomain**: `archive` (or your preferred name)
   - **Domain**: your Cloudflare zone
   - **Service type**: `HTTP`
   - **URL**: `caddy:80`

Cloudflare creates the proxied DNS record for the hostname. If you create the
record manually, use a proxied CNAME to
`<tunnel-id>.cfargotunnel.com`.

The service URL is `caddy:80` because Caddy runs on the Compose network. Do not
use `localhost:8000`; inside the `cloudflared` container, localhost is the
connector container itself.

## 2. Prepare the repository

```bash
git clone git@github.com:AlexTrinityBlock/apsor-archive.git
cd apsor-archive
```

The image build copies the committed `frontend/dist`. Rebuild the frontend
first if you changed frontend sources:

```bash
cd frontend
bun install --frozen-lockfile
bun run build
cd ..
```

## 3. Store the tunnel token

Create the secret file that Compose mounts read-only:

```bash
mkdir -p secrets
printf '%s' 'YOUR_TUNNEL_TOKEN' > secrets/cf_token.txt
chmod 644 secrets/cf_token.txt
chmod 755 secrets
```

Write the token without a trailing newline. The `cloudflared` container runs as
uid `65532` and must be able to read the file. Never put the token in
`environment:`, a committed `.env` file, or the repository.

See `secrets/README.md` for the same permission guidance.

## 4. Configure the public host and start

```bash
export APSOR_PUBLIC_HOST=archive.example.com
docker compose -f docker-compose.cloudflare-tunnel.yml up -d --build
```

`APSOR_PUBLIC_HOST` is used by Caddy for its host matcher. It is not the
tunnel DNS target; the target is the `caddy:80` service configured in the
Cloudflare dashboard.

The live deployment serves `archive.example.com`. The previous
`archive.example.com` is the **legacy hostname** and is no longer in
the current tunnel ingress. The examples here use `archive.example.com`; do not
change DNS or the tunnel ingress as part of an application rebrand.

The stack intentionally has no `ports:` mapping. Do not add one unless you are
debugging on a trusted host.

Check the services:

```bash
docker compose -f docker-compose.cloudflare-tunnel.yml ps
docker compose -f docker-compose.cloudflare-tunnel.yml logs -f cloudflare-tunnel caddy api
```

## 5. Verify the deployment

```bash
curl -fsS https://archive.example.com/api/v1/health
```

Expected shape:

```json
{"status":"ok","version":"0.1.0","database":"ok","cache":"ok","ai":"configured","embedding_provider":"hashing"}
```

Then open `https://archive.example.com` and complete the owner setup screen.
The cookie is configured with `APSOR_COOKIE_SECURE=true`; use HTTPS, not a
plain HTTP address.

Check the worker separately:

```bash
docker compose -f docker-compose.cloudflare-tunnel.yml logs -f worker
```

Upload a small text file and confirm the job reaches `ready` with the desired
chunk count. If the queue stays `queued`, the worker is not running or cannot
reach PostgreSQL.

## 6. Configure AI providers

The recommended path is the Settings page:

1. Sign in as the owner.
2. Open **Settings → Model providers**.
3. Configure the chat and embedding providers.
4. Use **Test connection** before saving if the provider supports it.

Keys are encrypted with Fernet before they are stored in PostgreSQL. The
encryption key is `APSOR_SECRET_KEY` or the auto-created
`/data/.secret_key` in the mounted data volume. Back up that key with the
database; without it, stored provider keys cannot be decrypted.

Environment variables remain a fallback for a fresh installation. For example,
a local secrets file can be mounted read-only:

```bash
mkdir -p .secrets
printf 'APSOR_DEEPSEEK_API_KEY=sk-your-key\n' > .secrets/deepseek.env
chmod 644 .secrets/deepseek.env
```

The Compose file mounts `./.secrets` read-only. Do not commit it.

The ingestion worker reads runtime settings from the database singleton. The
defaults are:

| Setting | Default |
|---|---|
| `poll_seconds` | 1.0 |
| `extract_workers` | 2 |
| `max_inflight_jobs` | 2 |
| `embedding_concurrency` | 6 |
| `chunk_target_chars` | 4,000 |
| `chunk_overlap_chars` | 500 |

Change them under **Settings → Ingestion runtime**. Worker changes apply to the
next loop or job. Changing chunk sizes affects future ingests only; existing
files keep their current boundaries until re-ingested.

## 7. Backups

The PostgreSQL named volume and the host `./data-cloudflare` directory are the
state that matters.

Database dump:

```bash
docker compose -f docker-compose.cloudflare-tunnel.yml exec -T db \
  pg_dump -U apsor -d apsor_archive | gzip > apsor-archive-$(date +%F).sql.gz
```

Data directory snapshot (stored originals and the Fernet key):

```bash
sudo tar czf apsor-archive-data-$(date +%F).tar.gz -C data-cloudflare .
```

Stop the stack before restoring both stores, then restore the database dump
with `pg_restore`/`psql` and extract the data archive back into
`./data-cloudflare`. Keep at least one backup of `/data/.secret_key` separate
from the database.

## 8. Security checklist

- Keep the Cloudflare Tunnel as the only public path. No router forwarding, no
  published API port, no public database or cache.
- Optionally put **Cloudflare Access** in front of the hostname. If you do,
  test the login flow and SSE/streaming responses through Access.
- Use Cloudflare WAF/rate-limiting rules for the hostname if it is exposed to
  the public internet.
- Keep `APSOR_COOKIE_SECURE=true` and use HTTPS.
- Keep `secrets/cf_token.txt` mode `644` and the `secrets` directory `755`;
  never commit either the token or provider keys.
- Rotate the tunnel token in the Cloudflare dashboard and update the secret
  file if it is exposed. Restart `cloudflare-tunnel` after rotation.
- The stack is single-owner. Login throttling is in-memory and assumes one API
  process.

## 9. Operations

Update after pulling a new revision:

```bash
git pull
cd frontend && bun install --frozen-lockfile && bun run build && cd ..
docker compose -f docker-compose.cloudflare-tunnel.yml up -d --build
```

View logs:

```bash
docker compose -f docker-compose.cloudflare-tunnel.yml logs -f --tail=200
```

Restart one service:

```bash
docker compose -f docker-compose.cloudflare-tunnel.yml restart api worker
```

The `worker` service shares the PostgreSQL queue with the API. If you ever run
an additional API process with its lifespan worker enabled, disable
`APSOR_INGEST_WORKER_ENABLED` on it to avoid duplicate claims.

## 10. Troubleshooting

| Symptom | Check |
|---|---|
| Cloudflare error 1033 | The tunnel is not connected. Check `cloudflared` logs and the token file. |
| Cloudflare error 502 | `cloudflared` is connected but Caddy/API is unhealthy. Check `caddy` and `api` logs; verify the public hostname service is `HTTP caddy:80`. |
| Hostname resolves but wrong site | The tunnel public hostname and `APSOR_PUBLIC_HOST` do not match, or another DNS record is proxied. |
| Login works but cookies are rejected | You are using HTTP, or `APSOR_COOKIE_SECURE` was changed. Use HTTPS and restart the API. |
| Uploads stay `queued` | Check `worker` logs, the `file_ingest_job` table, and that both `api` and `worker` use the same database. |
| Ingestion fails at embedding | Test the embedding provider in Settings; check outbound access and the provider key. The worker retries transient failures, then fails the job without publishing partial rows. |
| Long chat response returns 524 | Cloudflare's proxy has an origin timeout. Keep SSE data flowing; check Caddy/API logs. |
| Backup restore cannot decrypt provider keys | Restore `/data/.secret_key` from the same backup set, or re-enter the provider keys. |

## 11. Files used by this deployment

| File | Purpose |
|---|---|
| `docker-compose.cloudflare-tunnel.yml` | Tunnel stack |
| `docker/caddy/Caddyfile` | Reverse proxy and access logs |
| `docker/caddy/Dockerfile` | Non-root Caddy image |
| `secrets/cf_token.txt` | Tunnel token, gitignored |
| `.secrets/deepseek.env` | Optional provider fallback, gitignored |
| `Dockerfile` | API/worker image with the committed SPA build |

For local development, use `docker-compose.dev.yml`; for a host-only deployment
with a published loopback port, use `docker-compose.yml`.
