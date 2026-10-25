"""frequently used prompts

Revision ID: a3f7c9d1e5b2
Revises: e1a2b3c4d5f6
Create Date: 2026-10-25 00:00:00.000000

The plan's requested revision id ``f2b3c4d5e6a7`` is already used by
``f2b3c4d5e6a7_agent_approvals.py``. Alembic rejects duplicate revision ids,
so this migration uses a unique id while keeping the planned position in the
chain (after the provider-config migration ``e1a2b3c4d5f6``).
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "a3f7c9d1e5b2"
down_revision: str | None = "e1a2b3c4d5f6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SEED_PROMPTS: list[dict[str, object]] = [
    {
        "title": "Qing court",
        "prompt_text": "What does the archive hold about the Qing court?",
        "sort_order": 10,
    },
    {
        "title": "Summarise a file",
        "prompt_text": "Open a file from the library and summarise its key claims.",
        "sort_order": 20,
    },
    {
        "title": "Trace a memory",
        "prompt_text": "Trace the lineage of the most recent memory and explain what changed.",
        "sort_order": 30,
    },
]


def upgrade() -> None:
    op.create_table(
        "frequently_used_prompt",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("title", sa.String(length=80), nullable=False),
        sa.Column("prompt_text", sa.Text(), nullable=False),
        sa.Column(
            "sort_order",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "char_length(title) BETWEEN 1 AND 80",
            name=op.f("ck_frequently_used_prompt_title_length"),
        ),
        sa.CheckConstraint(
            "char_length(prompt_text) BETWEEN 1 AND 4000",
            name=op.f("ck_frequently_used_prompt_text_length"),
        ),
        sa.CheckConstraint(
            "sort_order >= 0",
            name=op.f("ck_frequently_used_prompt_sort_order"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_frequently_used_prompt")),
    )
    op.create_index(
        "ix_frequently_used_prompt_order",
        "frequently_used_prompt",
        ["sort_order", "id"],
        unique=False,
    )
    # Seed exactly the three shortcuts that used to be hard-coded in ChatIntro.
    # This runs once on upgrade; clearing every prompt in the UI stays empty.
    op.bulk_insert(
        sa.table(
            "frequently_used_prompt",
            sa.column("title", sa.String),
            sa.column("prompt_text", sa.Text),
            sa.column("sort_order", sa.Integer),
        ),
        SEED_PROMPTS,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_frequently_used_prompt_order",
        table_name="frequently_used_prompt",
    )
    op.drop_table("frequently_used_prompt")
