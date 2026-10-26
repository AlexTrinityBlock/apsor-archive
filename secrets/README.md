# Local secrets

There are two secret locations:

- `secrets/` holds the Cloudflare Tunnel token file named by
  `docker-compose.cloudflare-tunnel.yml`.
- `.secrets/` holds application env files that the API and worker read
  themselves: `deepseek.env`, `openai.env`, and `r2.env`. Compose mounts
  `.secrets/` read-only, so these values never become container environment
  variables.

The contents of both directories are gitignored (this README is the tracked
exception). Never put a secret in `environment:`, a committed `.env` file, a
URL, or a log.

## Cloudflare tunnel token

Create `secrets/cf_token.txt` with the tunnel token from the Cloudflare dashboard
(or `cloudflared tunnel token <tunnel-id>`).

The file must be readable by the `cloudflared` container, which runs as uid
65532. On Linux:

```bash
chmod 755 secrets
chmod 644 secrets/cf_token.txt
```

## R2 credentials

Create `.secrets/r2.env` with the S3-compatible access key pair for the private
bucket:

```text
APSOR_R2_ACCESS_KEY_ID=...
APSOR_R2_SECRET_ACCESS_KEY=...
```

The endpoint, bucket, region, and prefix are non-secret deployment values and may
come from the Compose environment or the same file. The production defaults are
`APSOR_R2_ENDPOINT_URL=https://<account-id>.r2.cloudflarestorage.com`,
`APSOR_R2_BUCKET=apsor-archive`, `APSOR_R2_REGION=auto`, and an empty
`APSOR_R2_PREFIX`. The app also accepts the legacy unprefixed
`R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `R2_ACCOUNT_ENDPOINT`, and
`R2_BUCKET` names used by local migration shells.

The API and worker run as uid `10001` and must be able to read the file:

```bash
chmod 755 .secrets
# Container uid 10001 needs read access; unrelated host users do not.
sudo chgrp 10001 .secrets/r2.env .secrets/deepseek.env .secrets/openai.env
chmod 640 .secrets/r2.env .secrets/deepseek.env .secrets/openai.env
```

On a single-user host, `644` also works, but `640` with group `10001` is the
safer default. Never make `.secrets` world-writable.

The bucket stays private; do not enable public access or presigned URLs, and do
not add a lifecycle expiry rule for `files/`. Back up `.secrets/r2.env`
separately from the bucket: it is required for restores and for the storage
migration CLI. `data/.secret_key` remains the Fernet master key for provider
credentials and is not an R2 secret.
