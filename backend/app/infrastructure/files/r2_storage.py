"""Cloudflare R2 storage adapter.

R2 is one S3-compatible provider, so the implementation lives in
``s3_storage.S3ObjectStorage``. This module keeps the historical import path and
the R2 defaults (``auto`` region, path-style addressing, no bucket creation).
"""

from __future__ import annotations

from pydantic import SecretStr

from app.infrastructure.files.s3_storage import ClientFactory, S3ObjectStorage


class R2FileStorage(S3ObjectStorage):
    """Persist original bytes in one private Cloudflare R2 bucket."""

    def __init__(
        self,
        *,
        endpoint_url: str,
        bucket: str,
        access_key_id: SecretStr,
        secret_access_key: SecretStr,
        region: str = "auto",
        prefix: str = "",
        client_factory: ClientFactory | None = None,
    ) -> None:
        super().__init__(
            endpoint_url=endpoint_url,
            bucket=bucket,
            access_key_id=access_key_id,
            secret_access_key=secret_access_key,
            region=region,
            prefix=prefix,
            addressing_style="path",
            create_bucket_if_missing=False,
            label="R2",
            client_factory=client_factory,
        )
