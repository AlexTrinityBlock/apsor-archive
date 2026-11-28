"""Construct the process-wide file storage router from Settings."""

from __future__ import annotations

import logging

from app.infrastructure.config.settings import Settings
from app.infrastructure.files.local_storage import LocalFileStorage
from app.infrastructure.files.r2_storage import R2FileStorage
from app.infrastructure.files.s3_storage import S3ObjectStorage
from app.infrastructure.files.storage_errors import StorageConfigurationError
from app.infrastructure.files.storage_router import StorageRouter

logger = logging.getLogger(__name__)


def build_r2_storage(settings: Settings) -> R2FileStorage:
    """Build the R2 adapter, failing with setting names only."""
    endpoint_url = settings.r2_endpoint_url
    bucket = settings.r2_bucket
    access_key_id = settings.r2_access_key_id
    secret_access_key = settings.r2_secret_access_key
    if (
        not settings.r2_configured
        or endpoint_url is None
        or bucket is None
        or access_key_id is None
        or secret_access_key is None
    ):
        missing = ", ".join(settings.r2_missing_settings)
        raise StorageConfigurationError(
            f"The r2 storage backend is missing configuration: {missing}."
        )
    return R2FileStorage(
        endpoint_url=endpoint_url,
        bucket=bucket,
        access_key_id=access_key_id,
        secret_access_key=secret_access_key,
        region=settings.r2_region,
        prefix=settings.r2_prefix,
    )


def build_s3_storage(settings: Settings) -> S3ObjectStorage:
    """Build the generic S3-compatible adapter, failing with setting names only."""
    endpoint_url = settings.s3_endpoint_url
    bucket = settings.s3_bucket
    access_key_id = settings.s3_access_key_id
    secret_access_key = settings.s3_secret_access_key
    if (
        not settings.s3_configured
        or endpoint_url is None
        or bucket is None
        or access_key_id is None
        or secret_access_key is None
    ):
        missing = ", ".join(settings.s3_missing_settings)
        raise StorageConfigurationError(
            f"The s3 storage backend is missing configuration: {missing}."
        )
    return S3ObjectStorage(
        endpoint_url=endpoint_url,
        bucket=bucket,
        access_key_id=access_key_id,
        secret_access_key=secret_access_key,
        region=settings.s3_region,
        prefix=settings.s3_prefix,
        addressing_style=settings.s3_addressing_style,
        create_bucket_if_missing=settings.s3_create_bucket,
        label="S3",
    )


def build_file_storage(settings: Settings) -> StorageRouter:
    """Build local + object-store adapters without touching the network.

    The local adapter is always present so a staged migration can still read
    legacy rows. R2 and S3 adapters are constructed whenever their settings are
    complete, so rows written to either keep reading after the default moves.
    A selected backend with missing settings fails fast at startup instead of
    silently writing to local disk.
    """
    backend = settings.resolved_storage_backend
    local = LocalFileStorage(settings.data_dir)
    r2 = build_r2_storage(settings) if settings.r2_configured or backend == "r2" else None
    s3 = build_s3_storage(settings) if settings.s3_configured or backend == "s3" else None

    ready = [name for name, adapter in (("R2", r2), ("S3", s3)) if adapter is not None]
    logger.info(
        "Object storage: default backend=%s, object adapters ready: %s.",
        backend,
        ", ".join(ready) or "none",
    )
    return StorageRouter(local=local, r2=r2, s3=s3, default_backend=backend)
