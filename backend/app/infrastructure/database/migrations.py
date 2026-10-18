"""Alembic migration runner used at application startup."""

from pathlib import Path

from alembic.config import Config

from alembic import command
from app.infrastructure.config.settings import BACKEND_ROOT


def upgrade_to_head(database_url: str) -> None:
    """Run every migration up to head against the configured database."""
    config = Config(str(Path(BACKEND_ROOT) / "alembic.ini"))
    config.set_main_option("script_location", str(Path(BACKEND_ROOT) / "alembic"))
    config.set_main_option("sqlalchemy.url", database_url)
    command.upgrade(config, "head")
