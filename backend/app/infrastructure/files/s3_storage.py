"""S3-compatible object-storage adapter (RustFS, Cloudflare R2, AWS S3, ...).

The same adapter serves every S3-compatible provider. Provider differences are
configuration only: the endpoint URL, region, and addressing style. RustFS and
most self-hosted servers need path-style addressing; R2 accepts both.

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
from collections.abc import Callable
from typing import Any, Final, Literal

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
_CLIENT_CACHE: dict[tuple[str, str, str, str, str], Any] = {}
_CLIENT_LOCK = threading.Lock()

AddressingStyle = Literal["path", "virtual"]
ClientFactory = Callable[..., Any]


class S3ObjectStorage:
    """Persist original bytes in one private S3-compatible bucket.

    ``label`` only shapes configuration error messages (for example ``R2`` or
    ``S3``); it never appears in API responses for runtime failures.
    ``create_bucket_if_missing`` lets a self-hosted store such as the bundled
    RustFS service start empty: the first write that meets ``NoSuchBucket``
    creates the bucket once and retries. Leave it off for managed providers,
    where the bucket is provisioned out of band.
    """

    def __init__(
        self,
        *,
        endpoint_url: str,
        bucket: str,
        access_key_id: SecretStr,
        secret_access_key: SecretStr,
        region: str = "auto",
        prefix: str = "",
        addressing_style: AddressingStyle = "path",
        create_bucket_if_missing: bool = False,
        label: str = "S3",
        client_factory: ClientFactory | None = None,
    ) -> None:
        endpoint = endpoint_url.strip().rstrip("/")
        resolved_bucket = bucket.strip()
        if not endpoint or not resolved_bucket:
            raise StorageConfigurationError(
                f"The {label} endpoint URL and bucket name are required."
            )
        if not endpoint.startswith(("https://", "http://")):
            raise StorageConfigurationError(f"The {label} endpoint URL must be an HTTP(S) URL.")
        if not access_key_id.get_secret_value().strip():
            raise StorageConfigurationError(f"The {label} access key ID is required.")
        if not secret_access_key.get_secret_value().strip():
            raise StorageConfigurationError(f"The {label} secret access key is required.")
        if addressing_style not in ("path", "virtual"):
            raise StorageConfigurationError(
                f"The {label} addressing style must be 'path' or 'virtual'."
            )

        self._endpoint_url = endpoint
        self._bucket = resolved_bucket
        self._region = region.strip() or "auto"
        self._access_key_id = access_key_id
        self._secret_access_key = secret_access_key
        self._prefix = prefix.strip().strip("/")
        self._addressing_style: AddressingStyle = addressing_style
        self._create_bucket_if_missing = create_bucket_if_missing
        self._client_factory = client_factory
        self._bucket_lock = threading.Lock()
        self._bucket_ready = False

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
            self._addressing_style,
        )
        factory = self._client_factory or boto3.client
        with _CLIENT_LOCK:
            client = _CLIENT_CACHE.get(cache_key)
            if client is None:
                client = factory(
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
                        s3={"addressing_style": self._addressing_style},
                    ),
                )
                _CLIENT_CACHE[cache_key] = client
            return client

    async def save(self, key: str, data: bytes) -> str:
        """Upload bytes and return the database storage key."""
        object_key = self._object_key(key)
        try:
            client = self._client()
            await asyncio.to_thread(self._put_object, client, object_key, data)
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

    def _put_object(self, client: Any, object_key: str, data: bytes) -> None:
        try:
            client.put_object(Bucket=self._bucket, Key=object_key, Body=data)
        except ClientError as exc:
            if not (self._create_bucket_if_missing and _is_missing_bucket(exc)):
                raise
            self._ensure_bucket(client)
            client.put_object(Bucket=self._bucket, Key=object_key, Body=data)

    def _ensure_bucket(self, client: Any) -> None:
        """Create the bucket once; a concurrent creator is not an error."""
        with self._bucket_lock:
            if self._bucket_ready:
                return
            try:
                client.create_bucket(Bucket=self._bucket)
            except ClientError as exc:
                code = str(exc.response.get("Error", {}).get("Code", ""))
                if code not in {"BucketAlreadyOwnedByYou", "BucketAlreadyExists"}:
                    raise
            self._bucket_ready = True

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


def _is_missing_bucket(exc: ClientError) -> bool:
    return str(exc.response.get("Error", {}).get("Code", "")) == "NoSuchBucket"


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
