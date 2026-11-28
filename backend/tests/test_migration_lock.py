"""Startup migrations are serialized by a PostgreSQL advisory lock."""

import threading
import time

from sqlalchemy import create_engine, text
from sqlalchemy.pool import NullPool

from app.infrastructure.database import migrations
from tests.conftest import TEST_DATABASE_URL


def test_second_process_waits_for_the_lock_then_upgrades(monkeypatch) -> None:
    calls: list[str] = []
    monkeypatch.setattr(migrations, "_run_upgrade", lambda url: calls.append(url))

    holder = create_engine(TEST_DATABASE_URL, poolclass=NullPool)
    with holder.connect() as connection:
        connection.execute(
            text("SELECT pg_advisory_lock(:key)"), {"key": migrations.MIGRATION_LOCK_KEY}
        )
        connection.commit()
        worker = threading.Thread(target=migrations.upgrade_to_head, args=(TEST_DATABASE_URL,))
        worker.start()
        time.sleep(0.5)
        # Blocked while another process holds the migration lock.
        assert calls == []
        connection.execute(
            text("SELECT pg_advisory_unlock(:key)"), {"key": migrations.MIGRATION_LOCK_KEY}
        )
        connection.commit()
        worker.join(timeout=10)
    holder.dispose()
    assert calls == [TEST_DATABASE_URL]

    # The lock is released afterwards: a fresh session can take it immediately.
    probe = create_engine(TEST_DATABASE_URL, poolclass=NullPool)
    with probe.connect() as connection:
        acquired = connection.execute(
            text("SELECT pg_try_advisory_lock(:key)"), {"key": migrations.MIGRATION_LOCK_KEY}
        ).scalar_one()
        assert acquired is True
        connection.execute(
            text("SELECT pg_advisory_unlock(:key)"), {"key": migrations.MIGRATION_LOCK_KEY}
        )
    probe.dispose()
