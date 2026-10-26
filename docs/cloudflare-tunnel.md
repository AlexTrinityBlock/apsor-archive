# Deploy Apsor Archive with Cloudflare Tunnel

This guide deploys the complete Apsor Archive stack on a Docker host and exposes
it through a Cloudflare Tunnel. The origin publishes **no inbound port**:
`cloudflared` makes outbound connections to Cloudflare, and Cloudflare reaches
the local Caddy reverse proxy over that tunnel. The deployed archive serves one
root account plus normal accounts, each with a private archive; originals are
stored on local disk or in a private Cloudflare R2 bucket.

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
                               ├── PostgreSQL 17 (private rows + RLS)
                               ├── Valkey
                               ├── host ./data-cloudflare (bound to /data)
                               ├── ./.secrets/r2.env (read-only R2 credentials)
                               └── Cloudflare R2 (private original bytes)
                                      ▲
                               worker process
```

Compose services:

| Service | Role |
|---|---|
| `db` | PostgreSQL 17 with a persistent named volume |
| `cache` | Valkey, used for the optional cache |
| `api` | FastAPI, serves the API and committed SPA build; local originals live in `./data-cloudflare` |
| `worker` | Dedicated durable-ingestion worker sharing the same host directory and R2 credentials |
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
- A Cloudflare R2 bucket for original bytes and an S3-compatible access key
  pair. The Compose files default to the private `apsor-archive` bucket. If you
  keep everything on local disk, set `APSOR_STORAGE_BACKEND=local`.
- A host data directory owned by the container uid:
  `mkdir -p data-cloudflare && sudo chown -R 10001:10001 data-cloudflare`.
- At least 2 GB of RAM for the database, API, worker, Caddy, and connector.
  The stack is designed for one root plus a small family or team on a single
  host; it is not a multi-tenant service.

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

### Object storage (R2)

The production Compose files default to `APSOR_STORAGE_BACKEND=r2`. The API and
worker read R2 credentials from `.secrets/r2.env`, mounted read-only; the file
must be readable by uid `10001`:

```bash
mkdir -p .secrets
cat > .secrets/r2.env <<'EOF'
APSOR_R2_ACCESS_KEY_ID=...
APSOR_R2_SECRET_ACCESS_KEY=...
EOF
chmod 755 .secrets
sudo chgrp 10001 .secrets/r2.env
chmod 640 .secrets/r2.env
```

The non-secret endpoint, bucket, region, and prefix come from the Compose
environment (`APSOR_R2_ENDPOINT_URL`, `APSOR_R2_BUCKET=apsor-archive`,
`APSOR_R2_REGION=auto`, `APSOR_R2_PREFIX`). The bucket stays private: do not
enable public access or presigned URLs, and do not add a lifecycle expiry rule
for `files/`. Keep the Fernet key (`/data/.secret_key` in the container,
`data-cloudflare/.secret_key` on the host) on local storage and back it up; it
is the master key for provider credentials.

For a trial with no R2 bucket, start with `APSOR_STORAGE_BACKEND=local`. To move
existing local bytes to R2, follow the maintenance procedure in
[Upgrade an existing archive](#12-upgrade-an-existing-archive) before switching
both services.

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

Then open `https://archive.example.com` and complete the root setup screen on a
fresh database. The cookie is configured with `APSOR_COOKIE_SECURE=true`; use
HTTPS, not a plain HTTP address. Sign in as root, open **Accounts**, create a
normal account, and confirm that the new account receives a one-time temporary
password and is forced to change it before any content loads. Confirm that a
normal account sees no **Accounts** item and no global Settings tabs.

If this is an upgrade of an existing archive rather than a fresh install, the
root password is reset during the maintenance procedure below; the temporary
password is delivered out of band and is not stored in this guide.

Check the worker separately:

```bash
docker compose -f docker-compose.cloudflare-tunnel.yml logs -f worker
```

Upload a small text file and confirm the job reaches `ready` with the desired
chunk count. If the queue stays `queued`, the worker is not running or cannot
reach PostgreSQL.

## 6. Configure AI providers

The recommended path is the Settings page:

1. Sign in as root.
2. Open **Settings → Model providers**.
3. Configure the chat and embedding providers.
4. Use **Test connection** before saving if the provider supports it.

Provider configuration is global deployment configuration. Normal accounts can
use AI features but cannot see the provider registry, change keys, or edit the
agent/ingestion runtime and system prompt. Keys are encrypted with Fernet before
they are stored in PostgreSQL. The
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

The backup set is PostgreSQL, the host `./data-cloudflare` directory (local
originals and `.secret_key`), the private R2 bucket contents, and the external
`.secrets/r2.env` credentials. Keep them together and verify a restore before
relying on them.

Database dump:

```bash
docker compose -f docker-compose.cloudflare-tunnel.yml exec -T db \
  pg_dump -U apsor -d apsor_archive | gzip > apsor-archive-$(date +%F).sql.gz
```

Data directory snapshot (local originals and the Fernet key):

```bash
sudo tar czf apsor-archive-data-$(date +%F).tar.gz -C data-cloudflare .
```

R2 backup:

- Enable bucket versioning, or run a scheduled `rclone`/S3 sync to a second
  private bucket.
- Never add a lifecycle expiry rule to `files/`. Soft delete keeps objects, so a
  database backup can usually still resolve an older key.
- Record the bucket name, endpoint, region, and prefix with the backup set. Do
  not record the secret access key in the database backup.

Stop the stack before restoring the database and data directory, then restore
the PostgreSQL dump with `pg_restore`/`psql`, extract the data archive back into
`./data-cloudflare`, and restore or re-sync the R2 objects. Keep at least one
backup of `/data/.secret_key` separate from the database; without it, encrypted
provider keys cannot be recovered.

## 8. Security checklist

- Complete first-run setup before exposing the public hostname. While no
  account exists, `/api/v1/auth/setup` is public by design; a fresh instance
  reachable through the tunnel can be claimed by the first visitor.
- Keep the Cloudflare Tunnel as the only public path. No router forwarding, no
  published API port, no public database or cache.
- Optionally put **Cloudflare Access** in front of the hostname. If you do,
  test the login flow and SSE/streaming responses through Access.
- Use Cloudflare WAF/rate-limiting rules for the hostname if it is exposed to
  the public internet.
- Keep `APSOR_COOKIE_SECURE=true` and use HTTPS.
- Keep `secrets/cf_token.txt` mode `644` and the `secrets` directory `755` so
  the cloudflared uid can read it. Keep `.secrets/r2.env` and provider env files
  mode `640` with group `10001`, and `.secrets` mode `755`, so the API/worker
  uid can read them without exposing them to unrelated host users. Never commit
  the tunnel token, R2 credentials, or provider keys.
- RLS is an API boundary, not a host boundary. The database login is a
  superuser for migrations/maintenance and the app switches roles per
  transaction; a local OS user or another container with database, Valkey, or
  secret-file access can bypass it. Keep the host and Compose network trusted,
  bind database/cache ports to localhost or an internal network, and use a
  strong database/cache credential on any shared host.
- Rotate the tunnel token in the Cloudflare dashboard and update the secret
  file if it is exposed. Restart `cloudflare-tunnel` after rotation. Rotate R2
  access keys in Cloudflare and restart both `api` and `worker`.
- The archive has exactly one root plus normal accounts. Root can manage
  accounts and global settings; normal data-API queries cannot cross accounts.
  Root password reset is a trusted-recovery capability that can transfer
  sign-in access, and root controls the global AI providers, so a malicious
  root is outside the RLS threat model. PostgreSQL forced RLS on `apsor_app` is
  the data boundary for normal request paths; do not grant that role
  `BYPASSRLS`, superuser, login, or another role.
- Temporary passwords are shown once and are never logged. Login throttling is
  in-memory and assumes one API process; do not scale to multiple API replicas
  without moving the throttle to Valkey.

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

Any storage-backend change must restart both `api` and `worker`; they build the
storage router independently. Keep reads mixed-safe: existing rows resolve by
their recorded `storage_backend`, so switching the environment does not move
bytes by itself.

## 10. Troubleshooting

| Symptom | Check |
|---|---|
| Cloudflare error 1033 | The tunnel is not connected. Check `cloudflared` logs and the token file. |
| Cloudflare error 502 | `cloudflared` is connected but Caddy/API is unhealthy. Check `caddy` and `api` logs; verify the public hostname service is `HTTP caddy:80`. |
| Hostname resolves but wrong site | The tunnel public hostname and `APSOR_PUBLIC_HOST` do not match, or another DNS record is proxied. |
| Login works but cookies are rejected | You are using HTTP, or `APSOR_COOKIE_SECURE` was changed. Use HTTPS and restart the API. |
| Uploads stay `queued` | Check `worker` logs, the `file_ingest_job` table, and that both `api` and `worker` use the same database. |
| Ingestion fails at embedding | Test the embedding provider in Settings; check outbound access and the provider key. The worker retries transient failures, then fails the job without publishing partial rows. |
| Upload or download fails only on R2 | Check `.secrets/r2.env` permissions (uid `10001`), bucket name, endpoint, region, and that both services restarted with the same `APSOR_STORAGE_BACKEND`. Run the storage migration `--verify`; provider diagnostics are deliberately hidden from API responses. |
| A normal user sees `403 forbidden` | The route is root-only by design. Accounts and global provider/agent/ingestion runtime settings are root surfaces. |
| A user is stuck after a temporary password | Root can reset the password in **Accounts**; reset revokes sessions and forces a new change at next sign-in. |
| Long chat response returns 524 | Cloudflare's proxy has an origin timeout. Keep SSE data flowing; check Caddy/API logs. |
| Backup restore cannot decrypt provider keys | Restore `/data/.secret_key` from the same backup set, or re-enter the provider keys. |

## 11. Files used by this deployment

| File | Purpose |
|---|---|
| `docker-compose.cloudflare-tunnel.yml` | Tunnel stack |
| `docker/caddy/Caddyfile` | Reverse proxy and access logs |
| `docker/caddy/Dockerfile` | Non-root Caddy image |
| `secrets/cf_token.txt` | Tunnel token, gitignored |
| `.secrets/r2.env` | R2 access key pair, gitignored, readable by uid `10001` |
| `.secrets/deepseek.env` | Optional provider fallback, gitignored |
| `Dockerfile` | API/worker image with the committed SPA build |

For local development, use `docker-compose.dev.yml`; for a host-only deployment
with a published loopback port, use `docker-compose.yml`.

## 12. Upgrade an existing archive

This is the short maintenance-window path for a deployment that predates
multi-user ownership and R2. Work from a full backup and do not delete local
bytes until the new version and the R2 copies are verified.

1. Announce the maintenance window and stop writes.
2. Back up PostgreSQL:

   ```bash
   docker compose -f docker-compose.cloudflare-tunnel.yml exec -T db \
     pg_dump -U apsor -d apsor_archive | gzip > apsor-pre-upgrade-$(date +%F).sql.gz
   pg_restore -l apsor-pre-upgrade-$(date +%F).sql.gz > /dev/null
   ```

3. Back up the data directory and copy `.secret_key` separately:

   ```bash
   sudo tar czf apsor-pre-upgrade-data-$(date +%F).tar.gz -C data-cloudflare .
   ```

4. Stop `api` and `worker`. Run the Alembic upgrade once as the owning login
   (the API lifespan also runs it on boot by default). The new head is
   `e8f1c4d2a7b9`; it creates `apsor_app`, backfills the oldest account as root,
   and enables RLS.
5. Make `.secrets/r2.env` readable by uid `10001`. For the first boot, run the
   Compose commands with `APSOR_STORAGE_BACKEND=local` so new writes stay on
   local disk until the copy is verified.
6. Start the new `api` and `worker` with local storage. Revoke every existing
   session, reset the root account to a generated temporary password with
   `must_change_password=true`, and deliver that password out of band. Do not
   store it in this guide, a ticket, or a committed file.
7. Run the storage migration in a one-off API container with `--copy`, then
   `--verify`:

   ```bash
   docker compose -f docker-compose.cloudflare-tunnel.yml run --rm \
     -e APSOR_STORAGE_BACKEND=local api \
     /app/backend/.venv/bin/python -m script.migrate_storage_to_r2 --copy
   docker compose -f docker-compose.cloudflare-tunnel.yml run --rm \
     -e APSOR_STORAGE_BACKEND=local api \
     /app/backend/.venv/bin/python -m script.migrate_storage_to_r2 --verify
   ```
8. Switch both services to `APSOR_STORAGE_BACKEND=r2` and restart them together.
9. Verify health, root sign-in, forced password change, account creation, and
   isolation: a normal account must not see another account's files, memories,
   conversations, or saved questions through the UI or a direct URL.
10. Keep the pre-upgrade database and data-directory backups through the
    rollback window. Only then run `--delete-local` to remove verified local
    bytes.

Rollback before local deletion: set `file.storage_backend` and retryable
`file_ingest_job.storage_backend` back to `local`, start both services with
`APSOR_STORAGE_BACKEND=local`, and restore the pre-upgrade data directory. Do not
delete the data directory or the R2 bucket until the new version is stable.
