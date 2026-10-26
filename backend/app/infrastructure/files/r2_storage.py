"""Cloudflare R2 storage adapter (S3-compatible).

One boto3 client is created lazily per process and shared by every request.
The synchronous client is safe for concurrent calls, and each call runs in a
worker thread so the event loop is never blocked. The constructor performs no
network I/O or client creation, which keeps startup and configuration checks
offline.
"""

from __future__ import annotations

import asyncio
import hashlib
import threading
from typing import Any, Final

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError
from pydantic import SecretStr

from app.infrastructure.files.storage_errors import (
    StorageConfigurationError,
    StorageObjectMissingError,
    StorageUnavailableError,
)

_MISSING_ERROR_CODES: Final[frozenset[str]] = frozenset({"NoSuchKey", "NotFound", "404"})
_CLIENT_CACHE: dict[tuple[str, str, str, str], Any] = {}
_CLIENT_LOCK = threading.Lock()


class R2FileStorage:
    """Persist original bytes in one private R2 bucket."""

    def __init__(
        self,
        *,
        endpoint_url: str,
        bucket: str,
        access_key_id: SecretStr,
        secret_access_key: SecretStr,
        region: str = "auto",
        prefix: str = "",
    ) -> None:
        endpoint = endpoint_url.strip().rstrip("/")
        resolved_bucket = bucket.strip()
        if not endpoint or not resolved_bucket:
            raise StorageConfigurationError("The R2 endpoint URL and bucket name are required.")
        if not endpoint.startswith(("https://", "http://")):
            raise StorageConfigurationError("The R2 endpoint URL must be an HTTP(S) URL.")
        if not access_key_id.get_secret_value().strip():
            raise StorageConfigurationError("The R2 access key ID is required.")
        if not secret_access_key.get_secret_value().strip():
            raise StorageConfigurationError("The R2 secret access key is required.")

        self._endpoint_url = endpoint
        self._bucket = resolved_bucket
        self._region = region.strip() or "auto"
        self._access_key_id = access_key_id
        self._secret_access_key = secret_access_key
        self._prefix = prefix.strip().strip("/")

    def _object_key(self, key: str) -> str:
        """Map an opaque database key to the bucket object key."""
        candidate = key.strip()
        if not candidate or candidate.startswith("/"):
            raise ValueError("Storage key must be a non-empty relative path.")
        if any(part in {".", ".."} for part in candidate.split("/")):
            raise ValueError("Storage key must not contain relative path segments.")
        if self._prefix:
            return f"{self._prefix}/{candidate}"
        return candidate

    def _client(self) -> Any:
        """Return the process-wide client, creating it on first use."""
        access_key_id = self._access_key_id.get_secret_value()
        secret_access_key = self._secret_access_key.get_secret_value()
        # Fingerprint the secret so a rotated credential causes a fresh client
        # without keeping the plaintext in the cache key.
        secret_fingerprint = hashlib.sha256(secret_access_key.encode("utf-8")).hexdigest()
        cache_key = (
            self._endpoint_url,
            access_key_id,
            secret_fingerprint,
            self._region,
        )
        with _CLIENT_LOCK:
            client = _CLIENT_CACHE.get(cache_key)
            if client is None:
                client = boto3.client(
                    "s3",
                    endpoint_url=self._endpoint_url,
                    aws_access_key_id=access_key_id,
                    aws_secret_access_key=secret_access_key,
                    region_name=self._region,
                    config=Config(
                        signature_version="s3v4",
                        retries={"max_attempts": 5, "mode": "standard"},
                        connect_timeout=10,
                        read_timeout=60,
                        s3={"addressing_style": "path"},
                    ),
                )
                _CLIENT_CACHE[cache_key] = client
            return client

    async def save(self, key: str, data: bytes) -> str:
        """Upload bytes and return the database storage key."""
        object_key = self._object_key(key)
        try:
            client = self._client()
            await asyncio.to_thread(
                client.put_object,
                Bucket=self._bucket,
                Key=object_key,
                Body=data,
            )
        except ClientError as exc:
            raise _translate_client_error(exc) from None
        except BotoCoreError:
            raise StorageUnavailableError() from None
        return key

    async def read(self, key: str) -> bytes:
        """Download one object; missing keys become a domain-safe error."""
        object_key = self._object_key(key)
        try:
            client = self._client()
            return await asyncio.to_thread(self._read_object, client, object_key)
        except ClientError as exc:
            raise _translate_client_error(exc) from None
        except BotoCoreError:
            raise StorageUnavailableError() from None

    async def delete(self, key: str) -> None:
        """Delete one object. S3 delete is idempotent for a missing key."""
        object_key = self._object_key(key)
        try:
            client = self._client()
            await asyncio.to_thread(
                client.delete_object,
                Bucket=self._bucket,
                Key=object_key,
            )
        except ClientError as exc:
            raise _translate_client_error(exc) from None
        except BotoCoreError:
            raise StorageUnavailableError() from None

    async def head_size(self, key: str) -> int | None:
        """Return the remote size, or ``None`` when the object is absent.

        The migration script uses this for an idempotent existence check before
        deciding whether an object needs to be uploaded again.
        """
        object_key = self._object_key(key)
        try:
            client = self._client()
            size = await asyncio.to_thread(self._head_object, client, object_key)
        except ClientError as exc:
            raise _translate_client_error(exc) from None
        except BotoCoreError:
            raise StorageUnavailableError() from None
        return size

    def _read_object(self, client: Any, object_key: str) -> bytes:
        response = client.get_object(Bucket=self._bucket, Key=object_key)
        body = response["Body"]
        try:
            return body.read()
        finally:
            body.close()

    def _head_object(self, client: Any, object_key: str) -> int | None:
        try:
            response = client.head_object(Bucket=self._bucket, Key=object_key)
        except ClientError as exc:
            if _is_missing_object(exc):
                return None
            raise
        return int(response.get("ContentLength", 0))


def _is_missing_object(exc: ClientError) -> bool:
    error = exc.response.get("Error", {})
    code = str(error.get("Code", ""))
    status = exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode")
    if code == "NoSuchBucket":
        # A missing bucket is a configuration/availability failure, not a
        # missing object. It must never make delete or upload look idempotent.
        return False
    return code in _MISSING_ERROR_CODES or status == 404


def _translate_client_error(
    exc: ClientError,
) -> StorageObjectMissingError | StorageUnavailableError:
    """Map botocore errors without copying provider messages into the error."""
    if _is_missing_object(exc):
        return StorageObjectMissingError()
    return StorageUnavailableError()
