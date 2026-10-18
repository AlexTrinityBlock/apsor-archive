"""Database engine ownership and the request-scoped transaction boundary."""

from collections.abc import AsyncIterator

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine


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


async def get_db_session(request: Request) -> AsyncIterator[AsyncSession]:
    """Yield the request session and commit once at the request boundary.

    FastAPI caches a dependency per request, so every slice shares this session.
    Services flush; only this exit point commits or rolls back.
    """
    database: Database = request.app.state.db
    async with database.session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
