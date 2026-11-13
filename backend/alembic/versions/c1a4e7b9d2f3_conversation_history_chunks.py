"""allow conversation history chunks

Revision ID: c1a4e7b9d2f3
Revises: b7e2d9f4a1c6
Create Date: 2026-11-13 00:00:00.000000

Conversation history reuses the existing flat ``chunk`` index as a fourth
source kind. ``source_id`` is the immutable ``agent_entry`` id, so the same
BM25/vector recall, owner-scoped RLS, and embedding reindex path apply.

Downgrade removes only the history rows; the windows can be rebuilt from the
append-only transcript by the history indexer after a re-upgrade.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "c1a4e7b9d2f3"
down_revision: str | None = "b7e2d9f4a1c6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint(
        op.f("ck_chunk_source_kind_valid"),
        "chunk",
        type_="check",
    )
    op.create_check_constraint(
        op.f("ck_chunk_source_kind_valid"),
        "chunk",
        "source_kind IN ('file', 'memory', 'summary', 'history')",
    )


def downgrade() -> None:
    # The old constraint cannot describe history rows, so remove them first.
    # chunk_ngram has an ON DELETE CASCADE foreign key to chunk.
    op.execute("DELETE FROM chunk WHERE source_kind = 'history'")
    op.drop_constraint(
        op.f("ck_chunk_source_kind_valid"),
        "chunk",
        type_="check",
    )
    op.create_check_constraint(
        op.f("ck_chunk_source_kind_valid"),
        "chunk",
        "source_kind IN ('file', 'memory', 'summary')",
    )
