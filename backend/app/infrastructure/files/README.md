# File storage

Original uploads are stored behind the three-method `FileStorageProtocol`
(`save`, `read`, `delete`). The infrastructure package mirrors that contract in
`storage_protocol.py`, so adapters and the router never import a module package.

- `local_storage.py` keeps bytes under `APSOR_DATA_DIR`.
- `r2_storage.py` stores bytes in a private Cloudflare R2 bucket. boto3 runs in
  a worker thread, the client is created lazily once per process, and the
  constructor performs no network I/O.
- `storage_router.py` chooses an adapter. New writes use
  `Settings.storage_backend`; reads use the row's `storage_backend`, falling
  back to the configured backend when the row value is null.
- `storage_factory.py` builds the router for both the API lifespan and the
  ingestion worker.

Callers that have a database row use the row value explicitly:

```python
storage = router.take(file.storage_backend)
data = await storage.read(file.storage_key)
```

`router.default_backend` is the value to persist with a new `storage_key`.

## Configuration

`APSOR_STORAGE_BACKEND` selects the backend for new writes (`local` or `r2`).
Non-secret R2 settings use `APSOR_R2_*`. Credentials are `SecretStr` values and
are never logged. The app reads `.secrets/r2.env` and `../.secrets/r2.env`
through the normal Settings env-file list. The local secret file may keep its
legacy `R2_ACCOUNT_ENDPOINT`, `R2_BUCKET`, `R2_ACCESS_KEY_ID`, and
`R2_SECRET_ACCESS_KEY` names. Container deployments mount `.secrets` read-only;
`r2.env` must be readable by uid 10001 (mode 644 or matching ownership).

The deployment bucket is the private `apsor-archive` bucket. The app never
issues presigned or public URLs, and the bucket must not have a lifecycle expiry
rule on `files/`. Back up the bucket with versioning or an object-sync job
alongside PostgreSQL, the data directory, and the separate Fernet key.

## Errors

`storage_errors.py` exposes provider-safe errors:

- `StorageObjectMissingError` for `NoSuchKey` / HTTP 404.
- `StorageUnavailableError` for credentials, permissions, missing buckets,
  timeouts, throttling, and every other botocore failure.
- `StorageConfigurationError` when a requested backend is not configured.

Provider messages are discarded, so API responses can never contain AWS
diagnostics, endpoint details, or credentials.

## Migration

See `backend/script/migrate_storage_to_r2.py`. Run it from `backend/` with
`--dry-run`, then `--copy`, `--verify`, and finally `--delete-local`. When the
host shell has no `APSOR_R2_BUCKET`, pass the non-secret value explicitly:

```bash
cd backend
APSOR_R2_BUCKET=apsor-archive uv run python -m script.migrate_storage_to_r2 --dry-run
```

Stop the API and worker first, and never run `--delete-local` without a
verified PostgreSQL and data-directory backup.
