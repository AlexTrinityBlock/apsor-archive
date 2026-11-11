"""temporary chat image attachments

Revision ID: b4e6d8f0a2c5
Revises: a3e7c1d9b2f4
Create Date: 2026-11-11 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "b4e6d8f0a2c5"
down_revision: str | None = "a3e7c1d9b2f4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "apsor_app"
SEQUENCE = "agent_chat_attachment_id_seq"


def upgrade() -> None:
    op.create_table(
        "agent_chat_attachment",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("conversation_id", sa.BigInteger(), nullable=True),
        sa.Column("entry_id", sa.BigInteger(), nullable=True),
        sa.Column("storage_key", sa.Text(), nullable=False),
        sa.Column("storage_backend", sa.String(length=16), nullable=False),
        sa.Column("file_name", sa.Text(), nullable=False),
        sa.Column("mime_type", sa.String(length=255), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("width", sa.Integer(), nullable=False),
        sa.Column("height", sa.Integer(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "mime_type IN ('image/png', 'image/jpeg', 'image/webp')",
            name=op.f("ck_agent_chat_attachment_mime_type_valid"),
        ),
        sa.CheckConstraint(
            "storage_backend IN ('local', 'r2')",
            name=op.f("ck_agent_chat_attachment_storage_backend_valid"),
        ),
        sa.CheckConstraint(
            "size_bytes > 0",
            name=op.f("ck_agent_chat_attachment_size_positive"),
        ),
        sa.CheckConstraint(
            "width > 0 AND height > 0",
            name=op.f("ck_agent_chat_attachment_dimensions_positive"),
        ),
        sa.ForeignKeyConstraint(
            ["conversation_id", "user_id"],
            ["agent_conversation.id", "agent_conversation.user_id"],
            name=op.f("fk_agent_chat_attachment_conversation_user"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["entry_id", "user_id"],
            ["agent_entry.id", "agent_entry.user_id"],
            name=op.f("fk_agent_chat_attachment_entry_user"),
            ondelete="SET NULL (entry_id)",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["app_user.id"],
            name=op.f("fk_agent_chat_attachment_user_id_app_user"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_agent_chat_attachment")),
        sa.UniqueConstraint(
            "storage_key",
            name=op.f("uq_agent_chat_attachment_storage_key"),
        ),
    )
    op.create_index(
        "ix_agent_chat_attachment_user_created",
        "agent_chat_attachment",
        ["user_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_agent_chat_attachment_user_entry",
        "agent_chat_attachment",
        ["user_id", "entry_id"],
        unique=False,
    )
    op.create_index(
        "ix_agent_chat_attachment_entry",
        "agent_chat_attachment",
        ["entry_id"],
        unique=False,
    )

    op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON agent_chat_attachment TO {APP_ROLE}")
    op.execute(f"GRANT USAGE, SELECT ON SEQUENCE {SEQUENCE} TO {APP_ROLE}")
    op.execute("ALTER TABLE agent_chat_attachment ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE agent_chat_attachment FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY agent_chat_attachment_owner ON agent_chat_attachment "
        f"FOR ALL TO {APP_ROLE} "
        f"USING (user_id = nullif(current_setting('app.user_id', true), '')::bigint) "
        f"WITH CHECK (user_id = nullif(current_setting('app.user_id', true), '')::bigint)"
    )


def downgrade() -> None:
    op.drop_index(
        "ix_agent_chat_attachment_entry",
        table_name="agent_chat_attachment",
    )
    op.drop_index(
        "ix_agent_chat_attachment_user_entry",
        table_name="agent_chat_attachment",
    )
    op.drop_index(
        "ix_agent_chat_attachment_user_created",
        table_name="agent_chat_attachment",
    )
    op.drop_table("agent_chat_attachment")
