"""Track pending chunk embeddings for the automatic backfill.

Revision ID: e7b2d5a9c4f1
Revises: b8e4d2f6a1c3
Create Date: 2026-11-28 12:00:00

Earlier writes stored a missing vector as JSON ``null``; the upgrade turns those
into SQL NULL (the model now uses ``none_as_null``). A chunk with a NULL
``embedding`` is pending: its text is indexed for keyword
search and the worker's backfill fills the vector in once the provider and the
account allowance allow it. ``embedding_failures`` counts only failures that
blame the text itself (HTTP 400/413/422), so a poison chunk stops being retried
while billing, quota, and outage failures never count against a row.

The ``chunk`` table is already owner-only under row-level security; a new
column and index need no policy or grant changes.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "e7b2d5a9c4f1"
down_revision: str | None = "b8e4d2f6a1c3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Older writes stored a missing vector as JSON ``null`` instead of SQL NULL.
    # Normalize them so every pending row looks the same to the backfill.
    op.execute("UPDATE chunk SET embedding = NULL WHERE embedding = 'null'::jsonb")
    op.add_column(
        "chunk",
        sa.Column(
            "embedding_failures",
            sa.SmallInteger(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )
    op.create_check_constraint(
        op.f("ck_chunk_embedding_failures_non_negative"),
        "chunk",
        "embedding_failures >= 0",
    )
    op.create_index(
        "ix_chunk_pending_embedding",
        "chunk",
        ["user_id", "id"],
        unique=False,
        postgresql_where=sa.text("embedding IS NULL"),
    )


def downgrade() -> None:
    op.drop_index(
        "ix_chunk_pending_embedding",
        table_name="chunk",
        postgresql_where=sa.text("embedding IS NULL"),
    )
    op.drop_constraint(
        op.f("ck_chunk_embedding_failures_non_negative"),
        "chunk",
        type_="check",
    )
    op.drop_column("chunk", "embedding_failures")
