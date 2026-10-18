"""Integration fixtures: one real PostgreSQL test database, sequential tests."""

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from app.infrastructure.config.settings import Settings
from app.main import create_app
from app.module.auth import model as auth_model  # noqa: F401
from app.module.knowledge.model import Base
from app.module.media import model as media_model  # noqa: F401

ADMIN_DATABASE_URL = "postgresql+psycopg://dendro:dendro@127.0.0.1:55432/dendromatrix"
TEST_DATABASE_URL = "postgresql+psycopg://dendro:dendro@127.0.0.1:55432/dendromatrix_test"
TEST_DATABASE_NAME = "dendromatrix_test"

TRUNCATE_STATEMENT = (
    "TRUNCATE TABLE chunk_ngram, chunk, tree_node, file, memory_summary, memory, "
    "media_ngram, media_asset, ai_provider_config, user_session, app_user "
    "RESTART IDENTITY CASCADE"
)

OWNER_USERNAME = "owner"
OWNER_PASSWORD = "correct-horse-battery"


def _ensure_database() -> None:
    admin_engine = create_engine(ADMIN_DATABASE_URL, isolation_level="AUTOCOMMIT")
    with admin_engine.connect() as connection:
        exists = connection.execute(
            text("SELECT 1 FROM pg_database WHERE datname = :name"),
            {"name": TEST_DATABASE_NAME},
        ).scalar_one_or_none()
        if exists is None:
            connection.execute(text(f'CREATE DATABASE "{TEST_DATABASE_NAME}"'))
    admin_engine.dispose()


@pytest.fixture(scope="session", autouse=True)
def test_database() -> Iterator[None]:
    """Create the test database and a fresh schema once per session."""
    _ensure_database()
    engine = create_engine(TEST_DATABASE_URL)
    with engine.begin() as connection:
        connection.execute(text("DROP SCHEMA public CASCADE"))
        connection.execute(text("CREATE SCHEMA public"))
        connection.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
    Base.metadata.create_all(engine)
    engine.dispose()
    yield


@pytest.fixture(autouse=True)
def clean_database(test_database: None, tmp_path: Path) -> Iterator[None]:
    """Reset every knowledge table before each test."""
    engine = create_engine(TEST_DATABASE_URL)
    with engine.begin() as connection:
        connection.execute(text(TRUNCATE_STATEMENT))
    engine.dispose()
    yield


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    """Settings that point at the test database and disable external AI."""
    return Settings(
        _env_file=None,
        database_url=TEST_DATABASE_URL,
        data_dir=tmp_path,
        static_dir=tmp_path / "no-spa",
        cors_origins=[],
        cache_url="memory://",
        cache_ttl_seconds=5,
        run_migrations=False,
        seed_demo=False,
        deepseek_api_key=None,
        ai_summary_enabled=False,
        auto_summary_threshold=999,
        gzip_minimum_size=1,
        embedding_provider="hashing",
        cookie_secure=False,
        login_attempt_limit=100,
    )


@pytest.fixture
def anonymous_client(settings: Settings) -> Iterator[TestClient]:
    """A TestClient with no owner account and no session."""
    with TestClient(create_app(settings)) as test_client:
        yield test_client


@pytest.fixture
def client(anonymous_client: TestClient) -> Iterator[TestClient]:
    """A TestClient with the owner account created and signed in."""
    response = anonymous_client.post(
        "/api/v1/auth/setup",
        json={
            "username": OWNER_USERNAME,
            "password": OWNER_PASSWORD,
            "confirm_password": OWNER_PASSWORD,
        },
    )
    assert response.status_code == 201, response.text
    yield anonymous_client
