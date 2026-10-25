"""rebrand embedding model identifier

Revision ID: b8d2e4f6a1c3
Revises: a3f7c9d1e5b2
Create Date: 2026-10-25 00:00:00.000000

The hashing embedder's vectors are unchanged; only its display identifier moved
from ``dendro-hash-384`` to ``apsor-hash-384``. Existing chunks are relabelled so
the stored model name matches the embedder that produced them.

Database and role renames are deployment operations, not schema migrations, so
they are deliberately absent here.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "b8d2e4f6a1c3"
down_revision: str | None = "a3f7c9d1e5b2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        sa.text(
            "UPDATE chunk SET embedding_model = 'apsor-hash-384' "
            "WHERE embedding_model = 'dendro-hash-384'"
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            "UPDATE chunk SET embedding_model = 'dendro-hash-384' "
            "WHERE embedding_model = 'apsor-hash-384'"
        )
    )
