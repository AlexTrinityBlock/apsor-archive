"""Integration fixtures: one migrated PostgreSQL test database, sequential tests.

The application request boundary always runs ``SET LOCAL ROLE apsor_app``, so
the test schema must be the real migrated schema. The fixture below resets the
disposable ``apsor_archive_test`` database, runs ``alembic upgrade head`` as the
owning login, and verifies the role, grants, RLS flags, and policies before any
test starts. ``Base.metadata.create_all`` is deliberately not used: it cannot
reproduce the role, grants, or policies that requests depend on.

The owning login is used only for migration, truncation, and fixture data.
Requests keep using ``apsor_app`` with transaction-local settings; nothing here
disables or bypasses row-level security.
"""

from collections.abc import Callable, Iterator
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass
from itertools import count
from pathlib import Path
from typing import Any

import pytest
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import Connection, Engine, create_engine, text
from sqlalchemy.exc import ProgrammingError

from alembic import command
from app.infrastructure.config.settings import Settings
from app.infrastructure.security.password_hasher import Argon2PasswordHasher
from app.main import create_app
from app.module.agent.service.system_prompt import default_sections
from app.module.auth.domain.auth_domain import AuthDomain

BACKEND_ROOT = Path(__file__).resolve().parents[1]

# Cluster maintenance and migrations connect to the maintenance database, not
# to the live archive. The disposable database name must stay test-only.
ADMIN_DATABASE_URL = "postgresql+psycopg://apsor:apsor@127.0.0.1:55432/postgres"
TEST_DATABASE_URL = "postgresql+psycopg://apsor:apsor@127.0.0.1:55432/apsor_archive_test"
TEST_DATABASE_NAME = "apsor_archive_test"
APP_ROLE = "apsor_app"

# Expected schema classification. A new application table must be added here
# and to the migration; otherwise the session fixture fails before tests run.
PRIVATE_TABLES: tuple[str, ...] = (
    "agent_approval",
    "agent_conversation",
    "agent_entry",
    "agent_run",
    "chunk",
    "chunk_ngram",
    "file",
    "file_ingest_job",
    "folder",
    "frequently_used_prompt",
    "memory",
    "memory_summary",
    "saved_question",
    "user_profile_card",
)
GLOBAL_TABLES: tuple[str, ...] = (
    "agent_config",
    "chat_provider_config",
    "embedding_provider_config",
    "ingest_config",
    "system_prompt_section",
    "web_fetch_provider_config",
    "web_search_provider_config",
)
AUTH_TABLES: tuple[str, ...] = ("app_user", "user_session")
ALEMBIC_TABLE = "alembic_version"
APPLICATION_TABLES = frozenset((*PRIVATE_TABLES, *GLOBAL_TABLES, *AUTH_TABLES))
EXPECTED_TABLES = APPLICATION_TABLES | {ALEMBIC_TABLE}

OWNER_USERNAME = "owner"
OWNER_PASSWORD = "correct-horse-battery"
USER_PASSWORD = "correct-horse-battery-user"

_TABLE_PRIVILEGES = frozenset({"SELECT", "INSERT", "UPDATE", "DELETE"})


@dataclass(frozen=True)
class UserClient:
    """A signed-in account and its independent cookie jar.

    User-factory instances own a separate app lifespan and ``TestClient``; the
    bootstrap root shares the ``client`` app. All clients share the migrated
    test database and the per-test data directory but never share cookies.
    """

    client: TestClient
    user_id: int
    username: str
    display_name: str
    role: str
    password: str


def _require(condition: object, message: str) -> None:
    """Fail fixture setup with a deterministic message."""
    if not condition:
        raise RuntimeError(message)


def _verify_app_role(connection: Connection) -> None:
    """Reject any application role that could bypass or weaken RLS."""
    role = (
        connection.execute(
            text("SELECT rolsuper, rolbypassrls, rolcanlogin FROM pg_roles WHERE rolname = :role"),
            {"role": APP_ROLE},
        )
        .mappings()
        .one_or_none()
    )
    _require(role is not None, f"{APP_ROLE} role is missing")
    assert role is not None
    _require(not role["rolsuper"], f"{APP_ROLE} must not be a superuser")
    _require(not role["rolbypassrls"], f"{APP_ROLE} must not have BYPASSRLS")
    _require(not role["rolcanlogin"], f"{APP_ROLE} must be NOLOGIN")
    memberships = connection.execute(
        text(
            "SELECT count(*) FROM pg_auth_members m "
            "JOIN pg_roles r ON r.oid = m.member WHERE r.rolname = :role"
        ),
        {"role": APP_ROLE},
    ).scalar_one()
    _require(memberships == 0, f"{APP_ROLE} must not inherit another role's privileges")


def _ensure_database() -> None:
    """Create the test database and the cluster-wide application role.

    The role is cluster-wide and may survive an earlier test database, so it is
    created only when missing. Its security attributes are verified instead of
    silently altered: a login, superuser, BYPASSRLS, or role membership would
    invalidate every RLS test.
    """
    _require(TEST_DATABASE_NAME != "apsor_archive", "refusing to use the live archive")
    _require(TEST_DATABASE_NAME.endswith("_test"), "test database name must end with '_test'")

    admin_engine = create_engine(ADMIN_DATABASE_URL, isolation_level="AUTOCOMMIT")
    try:
        with admin_engine.connect() as connection:
            exists = connection.execute(
                text("SELECT 1 FROM pg_database WHERE datname = :name"),
                {"name": TEST_DATABASE_NAME},
            ).scalar_one_or_none()
            if exists is None:
                connection.execute(text(f'CREATE DATABASE "{TEST_DATABASE_NAME}"'))

            role_exists = connection.execute(
                text("SELECT 1 FROM pg_roles WHERE rolname = :role"),
                {"role": APP_ROLE},
            ).scalar_one_or_none()
            if role_exists is None:
                connection.execute(text(f"CREATE ROLE {APP_ROLE} NOLOGIN"))

            _verify_app_role(connection)
    finally:
        admin_engine.dispose()


def _alembic_config() -> Config:
    """Build an Alembic config without loading the logging ini in-process."""
    config = Config()
    config.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))
    config.set_main_option("path_separator", "os")
    config.set_main_option("prepend_sys_path", str(BACKEND_ROOT))
    config.set_main_option("sqlalchemy.url", TEST_DATABASE_URL)
    return config


def _reset_schema(engine: Engine) -> None:
    """Drop the public schema so the migration chain always starts empty."""
    with engine.begin() as connection:
        connection.execute(text("SET LOCAL lock_timeout = '15s'"))
        connection.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
        connection.execute(text("CREATE SCHEMA public"))


def _verify_migrated_schema(engine: Engine) -> None:
    """Prove the migrated schema keeps the runtime security boundary intact."""
    with engine.connect() as connection:
        _verify_app_role(connection)

        tables = set(
            connection.execute(
                text(
                    "SELECT c.relname FROM pg_class c "
                    "JOIN pg_namespace n ON n.oid = c.relnamespace "
                    "WHERE n.nspname = 'public' AND c.relkind IN ('r', 'p')"
                )
            )
            .scalars()
            .all()
        )
        _require(
            tables == EXPECTED_TABLES,
            f"unexpected public tables: missing={sorted(EXPECTED_TABLES - tables)} "
            f"extra={sorted(tables - EXPECTED_TABLES)}",
        )

        _verify_grants(connection)
        _verify_rls_flags(connection)
        _verify_policies(connection)

        _require(
            connection.execute(
                text("SELECT has_schema_privilege(:role, 'public', 'USAGE')"),
                {"role": APP_ROLE},
            ).scalar_one(),
            f"{APP_ROLE} is missing USAGE on schema public",
        )
        _require(
            not connection.execute(
                text("SELECT has_schema_privilege(:role, 'public', 'CREATE')"),
                {"role": APP_ROLE},
            ).scalar_one(),
            f"{APP_ROLE} must not have CREATE on schema public",
        )

    # The request boundary's exact statement must work and must not be able to
    # rewrite Alembic history. Auth tables are readable before a user context.
    with engine.begin() as connection:
        connection.execute(text(f"SET LOCAL ROLE {APP_ROLE}"))
        _require(
            connection.execute(text("SELECT current_user")).scalar_one() == APP_ROLE,
            "SET LOCAL ROLE did not switch to the application role",
        )
        connection.execute(text("SELECT count(*) FROM app_user")).scalar_one()
        connection.execute(text("SELECT count(*) FROM system_prompt_section")).scalar_one()

    try:
        with engine.begin() as connection:
            connection.execute(text(f"SET LOCAL ROLE {APP_ROLE}"))
            connection.execute(text(f"SELECT version_num FROM {ALEMBIC_TABLE}"))
    except ProgrammingError:
        pass
    else:
        raise RuntimeError(f"{APP_ROLE} must not be able to read {ALEMBIC_TABLE}")


def _verify_grants(connection: Connection) -> None:
    """Check current table and sequence privileges for the application role."""
    grant_rows = connection.execute(
        text(
            "SELECT table_name, privilege_type FROM information_schema.role_table_grants "
            "WHERE grantee = :role AND table_schema = 'public'"
        ),
        {"role": APP_ROLE},
    ).all()
    table_privileges: dict[str, set[str]] = {}
    for table_name, privilege_type in grant_rows:
        table_privileges.setdefault(table_name, set()).add(privilege_type)

    for table in sorted(APPLICATION_TABLES):
        _require(table in table_privileges, f"{APP_ROLE} has no grants on {table}")
        _require(
            table_privileges[table] == set(_TABLE_PRIVILEGES),
            f"{APP_ROLE} has unexpected grants on {table}: {sorted(table_privileges[table])}",
        )
    _require(
        ALEMBIC_TABLE not in table_privileges,
        f"{APP_ROLE} must have no grants on {ALEMBIC_TABLE}",
    )

    sequence_rows = connection.execute(
        text(
            "SELECT c.relname, "
            "has_sequence_privilege(:role, c.oid, 'USAGE') AS has_usage, "
            "has_sequence_privilege(:role, c.oid, 'SELECT') AS has_select "
            "FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
            "WHERE n.nspname = 'public' AND c.relkind = 'S'"
        ),
        {"role": APP_ROLE},
    ).all()
    _require(sequence_rows, "no application sequences found after migration")
    _require(
        any(name == "agent_commit_seq" for name, _, _ in sequence_rows),
        "agent_commit_seq is missing after migration",
    )
    for name, has_usage, has_select in sequence_rows:
        _require(has_usage, f"{APP_ROLE} lacks USAGE on sequence {name}")
        _require(has_select, f"{APP_ROLE} lacks SELECT on sequence {name}")

    # The migration deliberately creates no ALTER DEFAULT PRIVILEGES grant for
    # apsor_app. A future table must arrive with an explicit grant and RLS
    # policy in its own migration; otherwise it stays fail-closed.


def _verify_rls_flags(connection: Connection) -> None:
    """Private and global tables must force RLS; auth tables must not use it."""
    rows = connection.execute(
        text(
            "SELECT c.relname, c.relrowsecurity, c.relforcerowsecurity "
            "FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
            "WHERE n.nspname = 'public' AND c.relkind IN ('r', 'p')"
        )
    ).all()
    flags = {name: (enabled, forced) for name, enabled, forced in rows}

    for table in (*PRIVATE_TABLES, *GLOBAL_TABLES):
        _require(
            flags.get(table) == (True, True),
            f"{table} must have RLS enabled and forced",
        )
    for table in (*AUTH_TABLES, ALEMBIC_TABLE):
        _require(
            flags.get(table) == (False, False),
            f"{table} must not have RLS enabled",
        )


def _verify_policies(connection: Connection) -> None:
    """Check the owner/global-write policy shapes and the auth-table exception."""
    rows = (
        connection.execute(
            text(
                "SELECT tablename, policyname, cmd, roles, qual, with_check "
                "FROM pg_policies WHERE schemaname = 'public'"
            )
        )
        .mappings()
        .all()
    )
    by_table: dict[str, list[Any]] = {}
    for row in rows:
        by_table.setdefault(row["tablename"], []).append(row)

    for table in PRIVATE_TABLES:
        entries = by_table.get(table, [])
        _require(
            len(entries) == 1 and entries[0]["policyname"] == f"{table}_owner",
            f"{table} must have exactly one {table}_owner policy",
        )
        entry = entries[0]
        _require(entry["cmd"] == "ALL", f"{table}_owner must be FOR ALL")
        _require(set(entry["roles"]) == {APP_ROLE}, f"{table}_owner has the wrong role")
        qual = entry["qual"] or ""
        check = entry["with_check"] or ""
        _require(
            "user_id" in qual and "app.user_id" in qual,
            f"{table}_owner USING clause is not owner-scoped",
        )
        _require(
            "user_id" in check and "app.user_id" in check,
            f"{table}_owner WITH CHECK clause is not owner-scoped",
        )

    for table in GLOBAL_TABLES:
        entries = by_table.get(table, [])
        _require(len(entries) == 2, f"{table} must have read and root-write policies")
        policies = {entry["policyname"]: entry for entry in entries}

        read = policies.get(f"{table}_read")
        _require(read is not None, f"{table}_read is missing")
        assert read is not None
        _require(read["cmd"] == "SELECT", f"{table}_read must be SELECT")
        _require(set(read["roles"]) == {APP_ROLE}, f"{table}_read has the wrong role")
        _require((read["qual"] or "").strip().lower() == "true", f"{table}_read must allow all")

        root_write = policies.get(f"{table}_root_write")
        _require(root_write is not None, f"{table}_root_write is missing")
        assert root_write is not None
        _require(root_write["cmd"] == "ALL", f"{table}_root_write must be FOR ALL")
        _require(
            set(root_write["roles"]) == {APP_ROLE},
            f"{table}_root_write has the wrong role",
        )
        qual = root_write["qual"] or ""
        check = root_write["with_check"] or ""
        _require(
            "app.user_role" in qual and "'root'" in qual,
            f"{table}_root_write USING clause is not root-scoped",
        )
        _require(
            "app.user_role" in check and "'root'" in check,
            f"{table}_root_write WITH CHECK clause is not root-scoped",
        )

    for table in (*AUTH_TABLES, ALEMBIC_TABLE):
        _require(not by_table.get(table), f"{table} must not have RLS policies")


@pytest.fixture(scope="session", autouse=True)
def test_database() -> Iterator[None]:
    """Migrate a fresh disposable database once per session and verify RLS."""
    _ensure_database()
    engine = create_engine(TEST_DATABASE_URL)
    try:
        _reset_schema(engine)
        command.upgrade(_alembic_config(), "head")
        _verify_migrated_schema(engine)
    finally:
        engine.dispose()
    yield


@pytest.fixture(scope="session")
def owner_engine(test_database: None) -> Iterator[Engine]:
    """A superuser/owner connection for migrations, truncation, and fixture data.

    Requests never use this engine: the application always switches its own
    connections to ``apsor_app``. A non-superuser table owner cannot seed
    forced-RLS tables or act as the maintenance connection, so the test cluster
    must provide one.
    """
    engine = create_engine(TEST_DATABASE_URL, pool_pre_ping=True)
    with engine.connect() as connection:
        privileged = connection.execute(
            text("SELECT rolsuper OR rolbypassrls FROM pg_roles WHERE rolname = current_user")
        ).scalar_one()
    if not privileged:
        engine.dispose()
        raise RuntimeError(
            "The test database login must be a superuser or have BYPASSRLS so "
            "migrations, truncation, and fixture seeding can bypass forced RLS."
        )
    yield engine
    engine.dispose()


@contextmanager
def rls_connection(
    engine: Engine,
    *,
    user_id: int | None = None,
    role: str | None = None,
) -> Iterator[Connection]:
    """Open a rollback-only ``apsor_app`` transaction for direct-SQL tests.

    This is the supported way to prove RLS from a test without weakening it.
    ``SET LOCAL ROLE`` is always applied; ``user_id`` and ``role`` become
    transaction-local settings exactly like the request path.
    """
    if role is not None and role not in {"root", "user"}:
        raise ValueError(f"Unsupported application role: {role!r}")
    with engine.connect() as connection:
        transaction = connection.begin()
        try:
            connection.execute(text(f"SET LOCAL ROLE {APP_ROLE}"))
            if user_id is not None:
                connection.execute(
                    text("SELECT set_config('app.user_id', :value, true)"),
                    {"value": str(user_id)},
                )
            if role is not None:
                connection.execute(
                    text("SELECT set_config('app.user_role', :value, true)"),
                    {"value": role},
                )
            yield connection
        finally:
            transaction.rollback()


def _seed_system_prompt_defaults(connection: Connection) -> None:
    """Reinsert the four seed rows a real migration writes into a fresh database.

    The rows are ordinary global sections; the test suite may edit, delete, or
    reorder them. The owner connection writes them because the fixture resets
    state outside a request transaction.
    """
    for index, section in enumerate(default_sections(), start=1):
        connection.execute(
            text(
                "INSERT INTO system_prompt_section (title, body, sort_order) "
                "VALUES (:title, :body, :sort_order)"
            ),
            {
                "title": section["title"],
                "body": section["body"],
                "sort_order": index * 10,
            },
        )


def _truncate_application_tables(connection: Connection) -> None:
    """Reset every application table, preserving the Alembic version row."""
    table_names = (
        connection.execute(
            text(
                "SELECT c.relname FROM pg_class c "
                "JOIN pg_namespace n ON n.oid = c.relnamespace "
                "WHERE n.nspname = 'public' AND c.relkind IN ('r', 'p') "
                "AND c.relname <> :alembic_table"
            ),
            {"alembic_table": ALEMBIC_TABLE},
        )
        .scalars()
        .all()
    )
    _require(
        set(table_names) == APPLICATION_TABLES,
        "truncation table set drifted from the expected application tables",
    )
    quoted = ", ".join(f'"{name}"' for name in table_names)
    connection.execute(text("SET LOCAL lock_timeout = '15s'"))
    connection.execute(text(f"TRUNCATE TABLE {quoted} RESTART IDENTITY CASCADE"))
    # agent_commit_seq is a standalone sequence used for cross-table ordering;
    # RESTART IDENTITY only resets sequences owned by the truncated tables.
    connection.execute(text("ALTER SEQUENCE agent_commit_seq RESTART WITH 1"))
    _seed_system_prompt_defaults(connection)


@pytest.fixture(autouse=True)
def clean_database(test_database: None, owner_engine: Engine) -> Iterator[None]:
    """Reset every application table before each test."""
    with owner_engine.begin() as connection:
        _truncate_application_tables(connection)
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
        deepseek_api_key=None,
        ai_summary_enabled=False,
        auto_summary_threshold=999,
        gzip_minimum_size=1,
        embedding_provider="hashing",
        cookie_secure=False,
        login_attempt_limit=100,
        ingest_worker_enabled=False,
    )


@pytest.fixture
def anonymous_client(settings: Settings) -> Iterator[TestClient]:
    """A TestClient with no owner account and no session."""
    with TestClient(create_app(settings)) as test_client:
        yield test_client


@pytest.fixture
def client(anonymous_client: TestClient) -> Iterator[TestClient]:
    """A TestClient with the bootstrap root account created and signed in."""
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


@pytest.fixture
def root_account(client: TestClient) -> UserClient:
    """The bootstrap root identity and its signed-in client."""
    response = client.get("/api/v1/auth/me")
    assert response.status_code == 200, response.text
    body = response.json()
    _require(body["role"] == "root", "the bootstrap account must have role='root'")
    return UserClient(
        client=client,
        user_id=int(body["user_id"]),
        username=str(body["username"]),
        display_name=str(body["display_name"] or body["username"]),
        role=str(body["role"]),
        password=OWNER_PASSWORD,
    )


@pytest.fixture
def client_factory(settings: Settings) -> Iterator[Callable[[], TestClient]]:
    """Create independent anonymous clients, each with its own app and cookies."""
    with ExitStack() as stack:

        def create() -> TestClient:
            return stack.enter_context(TestClient(create_app(settings)))

        yield create


def _insert_user(
    engine: Engine,
    *,
    username: str,
    display_name: str,
    password_hash: str,
    created_by_user_id: int,
    must_change_password: bool,
) -> int:
    """Insert one normal user as the owner; the request path stays RLS-scoped."""
    with engine.begin() as connection:
        return int(
            connection.execute(
                text(
                    "INSERT INTO app_user ("
                    "username, display_name, password_hash, role, is_active, "
                    "must_change_password, created_by_user_id, created_at, updated_at"
                    ") VALUES ("
                    ":username, :display_name, :password_hash, 'user', true, "
                    ":must_change_password, :created_by_user_id, now(), now()"
                    ") RETURNING id"
                ),
                {
                    "username": username,
                    "display_name": display_name,
                    "password_hash": password_hash,
                    "must_change_password": must_change_password,
                    "created_by_user_id": created_by_user_id,
                },
            ).scalar_one()
        )


@pytest.fixture
def user_client_factory(
    settings: Settings,
    owner_engine: Engine,
    root_account: UserClient,
) -> Iterator[Callable[..., UserClient]]:
    """Create normal accounts and return independently signed-in clients.

    Users are inserted as fixture data because account-management routes are a
    separate feature under test; login, session cookies, and password changes
    still go through the public API. Set ``must_change_password=True`` with
    ``complete_password_change=False`` to keep the forced-change state.
    """
    numbers = count(1)
    stack = ExitStack()

    def create(
        username: str | None = None,
        *,
        display_name: str | None = None,
        password: str = USER_PASSWORD,
        must_change_password: bool = False,
        complete_password_change: bool = True,
    ) -> UserClient:
        number = next(numbers)
        normalized_username = AuthDomain.normalize_username(username or f"member{number}")
        if not AuthDomain.is_valid_username(normalized_username):
            raise ValueError(f"Invalid test username: {normalized_username!r}")
        if not AuthDomain.is_valid_password(password):
            raise ValueError("Test user password must satisfy the authentication policy")

        resolved_display_name = (display_name or f"Member {number}").strip()
        if not resolved_display_name or len(resolved_display_name) > 80:
            raise ValueError("Test user display name must contain between 1 and 80 characters")

        user_id = _insert_user(
            owner_engine,
            username=normalized_username,
            display_name=resolved_display_name,
            password_hash=Argon2PasswordHasher().hash(password),
            created_by_user_id=root_account.user_id,
            must_change_password=must_change_password,
        )

        test_client = stack.enter_context(TestClient(create_app(settings)))
        login = test_client.post(
            "/api/v1/auth/login",
            json={"username": normalized_username, "password": password},
        )
        _require(login.status_code == 200, f"test user login failed: {login.text}")

        if must_change_password and complete_password_change:
            changed = test_client.post(
                "/api/v1/auth/password",
                json={
                    "current_password": password,
                    "new_password": password,
                    "confirm_password": password,
                },
            )
            _require(changed.status_code == 204, f"forced password change failed: {changed.text}")

        return UserClient(
            client=test_client,
            user_id=user_id,
            username=normalized_username,
            display_name=resolved_display_name,
            role="user",
            password=password,
        )

    try:
        yield create
    finally:
        stack.close()
