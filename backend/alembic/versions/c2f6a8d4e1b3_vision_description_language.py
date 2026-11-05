"""add the vision description language to the ingest config

Revision ID: c2f6a8d4e1b3
Revises: a1c3e5f7b9d2
Create Date: 2026-11-05 00:00:00.000000

The configured language applies to the visual description, caption, title,
summary, and tags produced by vision extraction. OCR text and table cell text
stay verbatim in the source language. The setting only affects future ingests.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c2f6a8d4e1b3"
down_revision: str | None = "a1c3e5f7b9d2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add the non-null language with an English default for existing rows."""
    op.add_column(
        "ingest_config",
        sa.Column(
            "vision_description_language",
            sa.String(length=80),
            server_default=sa.text("'English'"),
            nullable=False,
        ),
    )
    op.create_check_constraint(
        op.f("ck_ingest_config_vision_description_language_length"),
        "ingest_config",
        "char_length(btrim(vision_description_language)) BETWEEN 1 AND 80",
    )


def downgrade() -> None:
    """Drop the language constraint and column."""
    op.drop_constraint(
        op.f("ck_ingest_config_vision_description_language_length"),
        "ingest_config",
        type_="check",
    )
    op.drop_column("ingest_config", "vision_description_language")
