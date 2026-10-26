"""Construct the process-wide file storage router from Settings."""

from __future__ import annotations

import logging

from app.infrastructure.config.settings import Settings
from app.infrastructure.files.local_storage import LocalFileStorage
from app.infrastructure.files.r2_storage import R2FileStorage
from app.infrastructure.files.storage_errors import StorageConfigurationError
from app.infrastructure.files.storage_router import StorageRouter

logger = logging.getLogger(__name__)


def build_file_storage(settings: Settings) -> StorageRouter:
    """Build local + R2 adapters without touching the network.

    The local adapter is always present so a staged migration can still read
    legacy rows. R2 is only constructed when every required setting exists; a
    configured ``r2`` backend with missing credentials fails fast at startup
    instead of silently writing to local disk.
    """
    local = LocalFileStorage(settings.data_dir)
    r2: R2FileStorage | None = None
    if settings.r2_configured:
        endpoint_url = settings.r2_endpoint_url
        bucket = settings.r2_bucket
        access_key_id = settings.r2_access_key_id
        secret_access_key = settings.r2_secret_access_key
        if (
            endpoint_url is None
            or bucket is None
            or access_key_id is None
            or secret_access_key is None
        ):
            # ``r2_configured`` already guarantees these; keep the type checker
            # and future callers honest without logging any values.
            raise StorageConfigurationError("The R2 storage configuration is incomplete.")
        r2 = R2FileStorage(
            endpoint_url=endpoint_url,
            bucket=bucket,
            access_key_id=access_key_id,
            secret_access_key=secret_access_key,
            region=settings.r2_region,
            prefix=settings.r2_prefix,
        )
    elif settings.storage_backend == "r2":
        missing = ", ".join(settings.r2_missing_settings)
        raise StorageConfigurationError(
            f"The r2 storage backend is missing configuration: {missing}."
        )

    if r2 is None:
        logger.info("Object storage: local filesystem (R2 is not configured).")
    else:
        logger.info(
            "Object storage: default backend=%s, R2 adapter ready.",
            settings.storage_backend,
        )
    return StorageRouter(
        local=local,
        r2=r2,
        default_backend=settings.storage_backend,
    )
