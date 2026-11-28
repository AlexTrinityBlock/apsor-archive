"""agent web sources: short [web:wN] ids per conversation

Revision ID: e9b4c7d2a5f1
Revises: c4f9a2e7d1b8
Create Date: 2026-11-28 00:00:00.000000

``agent_web_source`` gives every public page a conversation's ``web_search``
or ``web_fetch`` saw a short, stable number, so the agent can cite it inline as
``[web:wN]`` and the reader can open it. Numbers follow first appearance and a
returning URL keeps its number. The table is private: ``user_id``, an
owner-safe composite foreign key to the conversation, the four DML grants for
``apsor_app``, and a forced owner-only RLS policy.

The migration also refreshes the two seeded system-prompt sections that
describe web citations, but only where a row still holds the exact seeded text:
a root-edited section is left alone.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "e9b4c7d2a5f1"
down_revision: str | None = "c4f9a2e7d1b8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "apsor_app"
TABLE = "agent_web_source"
OWNER_CHECK = "user_id = nullif(current_setting('app.user_id', true), '')::bigint"

# Exact seeded sentences, old → new. Only an unedited row contains the old one.
_INSTRUCTION_OLD = (
    "retrieval intent. Cite the source URL and the retrieval time; never "
    "present a web result as archive evidence.\n"
)
_INSTRUCTION_NEW = (
    "retrieval intent. Every web result and fetched page carries a short id "
    "such as w3; cite it inline as [web:w3] and mention the retrieval time "
    "when it matters. Never mix web ids with archive labels, and never "
    "present a web result as archive evidence.\n"
)
_PROTOCOL_OLD = (
    "data from a live fetch, and cite the url whenever you use it. "
)
_PROTOCOL_NEW = (
    "data from a live fetch. Each <result> and <web_fetch> carries an id such "
    "as w3; cite a page you use as [web:w3], never by pasting a bare url. "
)
_LABELS_OLD = (
    "- Cite exact labels: [file:id#chunk], [memory:id], and "
    "[summary:id]. Never invent an id or a label.\n"
)
_LABELS_NEW = (
    "- Cite exact labels: [file:id#chunk], [memory:id], [summary:id], and "
    "[web:wN] for web sources. Never invent an id or a label.\n"
)


def _replace(old: str, new: str) -> None:
    op.execute(
        sa.text(
            "UPDATE system_prompt_section "
            "SET body = replace(body, :old, :new) "
            "WHERE position(:old in body) > 0"
        ).bindparams(old=old, new=new)
    )


def upgrade() -> None:
    op.create_table(
        TABLE,
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("conversation_id", sa.BigInteger(), nullable=False),
        sa.Column("ref_no", sa.Integer(), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("ref_no > 0", name=op.f("ck_agent_web_source_ref_no_positive")),
        sa.CheckConstraint(
            "char_length(url) BETWEEN 1 AND 2048",
            name=op.f("ck_agent_web_source_url_length"),
        ),
        sa.ForeignKeyConstraint(
            ["conversation_id", "user_id"],
            ["agent_conversation.id", "agent_conversation.user_id"],
            name="fk_agent_web_source_conversation_user",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["app_user.id"],
            name=op.f("fk_agent_web_source_user_id_app_user"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_agent_web_source")),
        sa.UniqueConstraint(
            "user_id",
            "conversation_id",
            "url",
            name="uq_agent_web_source_conversation_url",
        ),
        sa.UniqueConstraint(
            "user_id",
            "conversation_id",
            "ref_no",
            name="uq_agent_web_source_conversation_ref",
        ),
    )
    op.create_index(
        "ix_agent_web_source_conversation",
        TABLE,
        ["user_id", "conversation_id"],
        unique=False,
    )
    op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {TABLE} TO {APP_ROLE}")
    op.execute(f"GRANT USAGE, SELECT ON SEQUENCE {TABLE}_id_seq TO {APP_ROLE}")
    op.execute(f"ALTER TABLE {TABLE} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {TABLE} FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY {TABLE}_owner ON {TABLE} FOR ALL TO {APP_ROLE} "
        f"USING ({OWNER_CHECK}) WITH CHECK ({OWNER_CHECK})"
    )

    _replace(_INSTRUCTION_OLD, _INSTRUCTION_NEW)
    _replace(_PROTOCOL_OLD, _PROTOCOL_NEW)
    _replace(_LABELS_OLD, _LABELS_NEW)


def downgrade() -> None:
    _replace(_LABELS_NEW, _LABELS_OLD)
    _replace(_PROTOCOL_NEW, _PROTOCOL_OLD)
    _replace(_INSTRUCTION_NEW, _INSTRUCTION_OLD)
    op.drop_index("ix_agent_web_source_conversation", table_name=TABLE)
    op.drop_table(TABLE)
