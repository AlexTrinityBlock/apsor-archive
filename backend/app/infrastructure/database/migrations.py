"""Alembic migration runner used at application startup.

The API and the dedicated worker both upgrade at startup. Without coordination
they race: one process applies a revision while the other tries the same DDL
and crashes (for example ``DuplicateColumn``). A PostgreSQL session-level
advisory lock serializes them: the first process migrates, the second waits,
then finds the database already at head and does nothing.
"""

from pathlib import Path

from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.pool import NullPool

from alembic import command
from app.infrastructure.config.settings import BACKEND_ROOT

# Fixed application-wide key ("APSR" in ASCII) for the startup migration lock.
MIGRATION_LOCK_KEY = 0x41505352


def _run_upgrade(database_url: str) -> None:
    config = Config(str(Path(BACKEND_ROOT) / "alembic.ini"))
    config.set_main_option("script_location", str(Path(BACKEND_ROOT) / "alembic"))
    config.set_main_option("sqlalchemy.url", database_url)
    command.upgrade(config, "head")


def upgrade_to_head(database_url: str) -> None:
    """Run every migration up to head, one process at a time.

    The lock is held on its own connection for the whole upgrade and released
    afterwards (or when the connection closes if the process dies).
    """
    engine = create_engine(database_url, poolclass=NullPool)
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT pg_advisory_lock(:key)"), {"key": MIGRATION_LOCK_KEY})
            connection.commit()
            try:
                _run_upgrade(database_url)
            finally:
                connection.execute(
                    text("SELECT pg_advisory_unlock(:key)"), {"key": MIGRATION_LOCK_KEY}
                )
                connection.commit()
    finally:
        engine.dispose()
