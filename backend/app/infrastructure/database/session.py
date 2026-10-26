"""Database engine ownership and RLS-scoped transaction helpers.

The application connects with the owning database login, but every transaction
that touches application data switches to the non-login ``apsor_app`` role and
sets the RLS context for that transaction. Transaction-local settings are
discarded on commit or rollback, so pooled connections cannot leak a previous
user's identity.

Session selection is part of the security boundary:

* :func:`public_session` - no user context; auth status/setup/login/health.
* :func:`user_session` - one owner's context; request services and workers.
* :func:`system_session` - root role only; global configuration tables.
* :func:`maintenance_session` - owner connection, no ``SET ROLE``; only
  explicit cross-owner maintenance: worker claim/recovery, agent startup
  recovery, and owner-id enumeration for embedding reindex.

``maintenance_session`` relies on the deployment login being the table owner or
a superuser, which is what makes ``FORCE ROW LEVEL SECURITY`` bypassable for
maintenance queries. Request-path API code must never use it, and a
maintenance query must never read or mutate another owner's private content;
it may only discover ids that are then processed in a scoped session.

Mid-workflow checkpoints inside a scoped session must use
:func:`commit_and_reapply`; a bare ``session.commit()`` drops the
transaction-local role and RLS settings.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import Request
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

APP_DATABASE_ROLE = "apsor_app"
ROLE_ROOT = "root"
ROLE_USER = "user"
VALID_ROLES = frozenset({ROLE_ROOT, ROLE_USER})

_USER_ID_SETTING = "app.user_id"
_USER_ROLE_SETTING = "app.user_role"


class Database:
    """Owns an async SQLAlchemy engine and its session factory."""

    def __init__(self, url: str, *, echo: bool = False) -> None:
        self.url = url
        self.engine = create_async_engine(url, echo=echo, pool_pre_ping=True)
        self.session_factory = async_sessionmaker(
            bind=self.engine,
            expire_on_commit=False,
            autoflush=False,
        )

    async def dispose(self) -> None:
        """Close pooled connections."""
        await self.engine.dispose()

    @asynccontextmanager
    async def public_session(self) -> AsyncIterator[AsyncSession]:
        """Open an ``apsor_app`` transaction without user context."""
        async with _scoped_session(self.session_factory, set_rls_role=True) as session:
            yield session

    @asynccontextmanager
    async def user_session(self, user_id: int, role: str) -> AsyncIterator[AsyncSession]:
        """Open a transaction scoped to one account's private archive.

        Do not call ``session.commit()`` directly inside this scope; a bare
        commit drops the transaction-local role and settings. Use
        :func:`commit_and_reapply` for mid-workflow checkpoints.
        """
        async with _scoped_session(
            self.session_factory,
            set_rls_role=True,
            user_id=user_id,
            role=role,
        ) as session:
            yield session

    @asynccontextmanager
    async def system_session(self) -> AsyncIterator[AsyncSession]:
        """Open a transaction that may read and write global configuration."""
        async with _scoped_session(
            self.session_factory,
            set_rls_role=True,
            role=ROLE_ROOT,
        ) as session:
            yield session

    @asynccontextmanager
    async def maintenance_session(self) -> AsyncIterator[AsyncSession]:
        """Open an owner transaction outside RLS for explicit maintenance only."""
        async with _scoped_session(self.session_factory, set_rls_role=False) as session:
            yield session


@asynccontextmanager
async def _scoped_session(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    set_rls_role: bool,
    user_id: int | None = None,
    role: str | None = None,
) -> AsyncIterator[AsyncSession]:
    """Open a session, apply transaction-local context, and own commit/rollback.

    The context is deliberately transaction-local so a pooled connection can
    never leak it. Callers must not call ``session.commit()`` directly for
    checkpoints inside this scope; use :func:`commit_and_reapply`, which
    restores the RLS role and settings immediately after committing.
    """
    if role is not None and role not in VALID_ROLES:
        raise ValueError(f"Unsupported application role: {role!r}")
    async with session_factory() as session:
        try:
            if set_rls_role:
                await _set_local_role(session)
            if user_id is not None:
                await _set_local_setting(session, _USER_ID_SETTING, str(user_id))
            if role is not None:
                await _set_local_setting(session, _USER_ROLE_SETTING, role)
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def _set_local_role(session: AsyncSession) -> None:
    """Switch the current transaction to the RLS application role.

    The role name is a module constant, never user input, so it is safe to
    interpolate into the statement.
    """
    await session.execute(text(f"SET LOCAL ROLE {APP_DATABASE_ROLE}"))


async def _set_local_setting(session: AsyncSession, name: str, value: str) -> None:
    """Set a transaction-local PostgreSQL setting with a bound value."""
    await session.execute(
        text("SELECT set_config(:name, :value, true)"),
        {"name": name, "value": value},
    )


async def apply_user_context(session: AsyncSession, user_id: int, role: str) -> None:
    """Attach an authenticated account to an already-open request transaction.

    ``get_current_user`` calls this after resolving the cookie session against
    the auth tables, which deliberately have no RLS.
    """
    if role not in VALID_ROLES:
        raise ValueError(f"Unsupported application role: {role!r}")
    await _set_local_role(session)
    await _set_local_setting(session, _USER_ID_SETTING, str(user_id))
    await _set_local_setting(session, _USER_ROLE_SETTING, role)


async def commit_and_reapply(session: AsyncSession, user_id: int, role: str) -> None:
    """Commit a workflow checkpoint and immediately restore the scoped context.

    ``SET LOCAL ROLE`` and ``set_config(..., true)`` are transaction-scoped.
    A plain ``session.commit()`` inside a user-scoped session therefore drops
    the ``apsor_app`` role and the RLS settings. The connection reverts to the
    owning login (normally a superuser), which bypasses row-level security and
    can silently read or mutate every archive. Use this helper for checkpoints
    in ingestion or agent workflows instead of calling ``commit()`` directly.
    The request boundary still commits once on exit via ``get_db_session``.
    """
    await session.commit()
    await apply_user_context(session, user_id, role)


@asynccontextmanager
async def public_session(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncSession]:
    """Yield an ``apsor_app`` session with no user context."""
    async with _scoped_session(session_factory, set_rls_role=True) as session:
        yield session


@asynccontextmanager
async def user_session(
    session_factory: async_sessionmaker[AsyncSession],
    user_id: int,
    role: str,
) -> AsyncIterator[AsyncSession]:
    """Yield an ``apsor_app`` session scoped to one account.

    Checkpoint with :func:`commit_and_reapply`; a bare ``commit()`` would drop
    the transaction-local role and settings and bypass RLS.
    """
    if role not in VALID_ROLES:
        raise ValueError(f"Unsupported application role: {role!r}")
    async with _scoped_session(
        session_factory,
        set_rls_role=True,
        user_id=user_id,
        role=role,
    ) as session:
        yield session


@asynccontextmanager
async def system_session(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncSession]:
    """Yield an ``apsor_app`` session allowed to write global configuration."""
    async with _scoped_session(
        session_factory,
        set_rls_role=True,
        role=ROLE_ROOT,
    ) as session:
        yield session


@asynccontextmanager
async def maintenance_session(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncSession]:
    """Yield an owner session without RLS for explicit maintenance only."""
    async with _scoped_session(session_factory, set_rls_role=False) as session:
        yield session


async def get_db_session(request: Request) -> AsyncIterator[AsyncSession]:
    """Yield the request session and commit once at the request boundary.

    FastAPI caches a dependency per request, so every slice shares this session.
    It starts as ``apsor_app`` with no user context; authentication applies the
    resolved account with :func:`apply_user_context` on the same transaction.
    Services flush; only this exit point commits or rolls back.
    """
    database: Database = request.app.state.db
    async with database.public_session() as session:
        yield session
