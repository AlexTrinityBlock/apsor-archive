"""S3-compatible storage selection and adapter behavior, fully offline."""

import asyncio
from pathlib import Path
from typing import Any

import pytest
from botocore.exceptions import ClientError
from pydantic import SecretStr

from app.infrastructure.config.settings import Settings
from app.infrastructure.files.local_storage import LocalFileStorage
from app.infrastructure.files.r2_storage import R2FileStorage
from app.infrastructure.files.s3_storage import S3ObjectStorage
from app.infrastructure.files.storage_errors import (
    StorageConfigurationError,
    StorageUnavailableError,
)
from app.infrastructure.files.storage_factory import build_file_storage
from app.infrastructure.files.storage_router import StorageRouter, normalize_backend

_R2 = {
    "r2_endpoint_url": "https://r2.invalid",
    "r2_bucket": "r2-bucket",
    "r2_access_key_id": SecretStr("r2-access"),
    "r2_secret_access_key": SecretStr("r2-secret-value"),
}
_S3 = {
    "s3_endpoint_url": "http://rustfs.invalid:9000",
    "s3_bucket": "s3-bucket",
    "s3_access_key_id": SecretStr("s3-access"),
    "s3_secret_access_key": SecretStr("s3-secret-value"),
}


def _settings(tmp_path: Path, **values: Any) -> Settings:
    return Settings(_env_file=None, data_dir=tmp_path, **values)


class _FakeS3Client:
    """Minimal S3 surface; records the factory kwargs that built it."""

    def __init__(self, *, bucket_exists: bool = True, **kwargs: Any) -> None:
        self.kwargs = kwargs
        self.buckets: set[str] = set()
        self.bucket_exists = bucket_exists
        self.objects: dict[tuple[str, str], bytes] = {}
        self.create_calls = 0

    def _error(self, code: str, status: int) -> ClientError:
        return ClientError(
            {"Error": {"Code": code}, "ResponseMetadata": {"HTTPStatusCode": status}},
            "S3Operation",
        )

    def put_object(self, *, Bucket: str, Key: str, Body: bytes) -> None:
        if not self.bucket_exists and Bucket not in self.buckets:
            raise self._error("NoSuchBucket", 404)
        self.objects[(Bucket, Key)] = bytes(Body)

    def create_bucket(self, *, Bucket: str) -> None:
        self.create_calls += 1
        self.buckets.add(Bucket)


def _storage(fake: _FakeS3Client, **overrides: Any) -> S3ObjectStorage:
    def factory(*_: Any, **kwargs: Any) -> _FakeS3Client:
        fake.kwargs = kwargs
        return fake

    values: dict[str, Any] = {
        "endpoint_url": "http://rustfs.invalid:9000",
        "bucket": f"bucket-{id(fake)}",
        "access_key_id": SecretStr("access"),
        "secret_access_key": SecretStr(f"secret-{id(fake)}"),
        "client_factory": factory,
    }
    values.update(overrides)
    return S3ObjectStorage(**values)


def test_rustfs_alias_and_auto_resolution(tmp_path: Path) -> None:
    """``rustfs`` means ``s3``; ``auto`` prefers an existing R2 deployment."""
    assert _settings(tmp_path, storage_backend="RustFS").storage_backend == "s3"
    assert normalize_backend("rustfs") == "s3"
    assert _settings(tmp_path).resolved_storage_backend == "local"
    assert _settings(tmp_path, storage_backend="auto").resolved_storage_backend == "local"
    assert (
        _settings(tmp_path, storage_backend="auto", **_S3).resolved_storage_backend == "s3"
    )
    both = _settings(tmp_path, storage_backend="auto", **_R2, **_S3)
    assert both.resolved_storage_backend == "r2"


def test_factory_keeps_r2_rows_readable_while_s3_is_the_default(tmp_path: Path) -> None:
    """A mixed archive reads R2 rows after new writes move to RustFS."""
    router = build_file_storage(_settings(tmp_path, storage_backend="s3", **_R2, **_S3))
    assert router.default_backend == "s3"
    assert isinstance(router.take("r2"), R2FileStorage)
    assert isinstance(router.take("s3"), S3ObjectStorage)
    assert not isinstance(router.take("s3"), R2FileStorage)
    assert isinstance(router.take("local"), LocalFileStorage)


def test_selected_backend_without_settings_fails_with_names_only(tmp_path: Path) -> None:
    """Missing S3 settings are reported by name, never by value."""
    with pytest.raises(StorageConfigurationError) as error:
        build_file_storage(
            _settings(
                tmp_path,
                storage_backend="s3",
                s3_endpoint_url="http://rustfs.invalid:9000",
                s3_secret_access_key=SecretStr("leaky-secret"),
            )
        )
    message = str(error.value)
    assert "s3_bucket" in message and "s3_access_key_id" in message
    assert "leaky-secret" not in message
    assert "rustfs.invalid" not in message


def test_router_rejects_unconfigured_s3_rows(tmp_path: Path) -> None:
    """A row naming s3 fails safely when this process has no S3 adapter."""
    router = StorageRouter(local=LocalFileStorage(tmp_path), r2=None, default_backend="local")
    with pytest.raises(StorageConfigurationError):
        router.take("s3")
    with pytest.raises(StorageConfigurationError):
        StorageRouter(local=LocalFileStorage(tmp_path), r2=None, default_backend="s3")


def test_s3_adapter_creates_a_missing_bucket_once_when_enabled() -> None:
    """The bundled RustFS starts empty; the first write creates its bucket."""
    fake = _FakeS3Client(bucket_exists=False)
    storage = _storage(fake, create_bucket_if_missing=True, prefix="archive")

    async def scenario() -> None:
        assert await storage.save("users/1/a.txt", b"one") == "users/1/a.txt"
        assert await storage.save("users/1/b.txt", b"two") == "users/1/b.txt"

    asyncio.run(scenario())
    assert fake.create_calls == 1
    assert set(fake.objects) == {
        (next(iter(fake.buckets)), "archive/users/1/a.txt"),
        (next(iter(fake.buckets)), "archive/users/1/b.txt"),
    }
    assert fake.kwargs["config"].s3["addressing_style"] == "path"


def test_s3_adapter_never_creates_buckets_by_default() -> None:
    """Managed providers keep their bucket provisioning out of band."""
    fake = _FakeS3Client(bucket_exists=False)
    storage = _storage(fake, addressing_style="virtual")

    with pytest.raises(StorageUnavailableError) as error:
        asyncio.run(storage.save("users/1/a.txt", b"one"))
    assert fake.create_calls == 0
    assert "bucket" not in str(error.value).lower()
    assert fake.kwargs["config"].s3["addressing_style"] == "virtual"


def test_s3_adapter_validates_configuration() -> None:
    """Bad endpoints and addressing styles fail before any client exists."""
    fake = _FakeS3Client()
    with pytest.raises(StorageConfigurationError):
        _storage(fake, endpoint_url="ftp://rustfs.invalid")
    with pytest.raises(StorageConfigurationError):
        _storage(fake, addressing_style="dns")
