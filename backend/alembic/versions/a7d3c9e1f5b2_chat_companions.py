"""chat companions: custom sprite companions and the per-account preference

Revision ID: a7d3c9e1f5b2
Revises: c7a3e9f1d5b2
Create Date: 2026-11-28 00:00:00.000000

Three private tables, each with ``user_id``, a forced owner-only RLS policy,
and the four DML grants for ``apsor_app``:

- ``companion``: one user-created companion. ``(id, user_id)`` is unique so
  frames can reference it through an owner-safe composite foreign key.
- ``companion_frame``: one encoded AVIF (fallback WebP) frame of one action. Deleting a
  companion cascades to its frames; the service removes the objects.
- ``companion_preference``: one row per account (primary key ``user_id``).

The action list is embedded on purpose; a migration must stay reproducible
even if the application vocabulary changes later.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "a7d3c9e1f5b2"
down_revision: str | None = "c7a3e9f1d5b2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "apsor_app"
ACTIONS = (
    "'idle', 'greet', 'listening', 'thinking', 'searching', 'reading', "
    "'writing', 'calculating', 'browsing', 'presenting', 'speaking', "
    "'waiting', 'success', 'confused', 'sleeping', 'held'"
)
OWNER_CHECK = "user_id = nullif(current_setting('app.user_id', true), '')::bigint"


def _secure(table: str, sequence: str | None) -> None:
    op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO {APP_ROLE}")
    if sequence is not None:
        op.execute(f"GRANT USAGE, SELECT ON SEQUENCE {sequence} TO {APP_ROLE}")
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY {table}_owner ON {table} FOR ALL TO {APP_ROLE} "
        f"USING ({OWNER_CHECK}) WITH CHECK ({OWNER_CHECK})"
    )


def upgrade() -> None:
    op.create_table(
        "companion",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("name", sa.String(length=40), nullable=False),
        sa.Column("gender", sa.String(length=16), nullable=True),
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
            "char_length(name) BETWEEN 1 AND 40",
            name=op.f("ck_companion_name_length"),
        ),
        sa.CheckConstraint(
            "gender IS NULL OR gender IN ('female', 'male', 'other')",
            name=op.f("ck_companion_gender_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["app_user.id"],
            name=op.f("fk_companion_user_id_app_user"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_companion")),
        sa.UniqueConstraint("id", "user_id", name="uq_companion_id_user_id"),
    )
    op.create_index("ix_companion_user_id", "companion", ["user_id", "id"], unique=False)

    op.create_table(
        "companion_frame",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("companion_id", sa.BigInteger(), nullable=False),
        sa.Column("action", sa.String(length=32), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("storage_backend", sa.String(length=16), nullable=False),
        sa.Column("storage_key", sa.Text(), nullable=False),
        sa.Column("mime_type", sa.String(length=32), nullable=False),
        sa.Column("width", sa.Integer(), nullable=False),
        sa.Column("height", sa.Integer(), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            f"action IN ({ACTIONS})",
            name=op.f("ck_companion_frame_action_valid"),
        ),
        sa.CheckConstraint(
            "position >= 0",
            name=op.f("ck_companion_frame_position_non_negative"),
        ),
        sa.CheckConstraint(
            "storage_backend IN ('local', 'r2', 's3')",
            name=op.f("ck_companion_frame_storage_backend_valid"),
        ),
        sa.CheckConstraint(
            "mime_type IN ('image/avif', 'image/webp')",
            name=op.f("ck_companion_frame_mime_type_valid"),
        ),
        sa.CheckConstraint(
            "width BETWEEN 1 AND 384 AND height BETWEEN 1 AND 576",
            name=op.f("ck_companion_frame_dimensions_valid"),
        ),
        sa.CheckConstraint(
            "size_bytes > 0",
            name=op.f("ck_companion_frame_size_positive"),
        ),
        sa.CheckConstraint(
            "sha256 ~ '^[0-9a-f]{64}$'",
            name=op.f("ck_companion_frame_sha256_hex"),
        ),
        sa.ForeignKeyConstraint(
            ["companion_id", "user_id"],
            ["companion.id", "companion.user_id"],
            name="fk_companion_frame_companion_user",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["app_user.id"],
            name=op.f("fk_companion_frame_user_id_app_user"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_companion_frame")),
        sa.UniqueConstraint("storage_key", name="uq_companion_frame_storage_key"),
    )
    op.create_index(
        "ix_companion_frame_owner_action",
        "companion_frame",
        ["user_id", "companion_id", "action", "position"],
        unique=False,
    )
    op.create_index(
        "ix_companion_frame_companion",
        "companion_frame",
        ["companion_id"],
        unique=False,
    )

    op.create_table(
        "companion_preference",
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("selected", sa.String(length=64), nullable=True),
        sa.Column("enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("motion", sa.String(length=16), server_default=sa.text("'full'"), nullable=False),
        sa.Column("position_x", sa.Float(), nullable=True),
        sa.Column("position_y", sa.Float(), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "motion IN ('full', 'reduced', 'off')",
            name=op.f("ck_companion_preference_motion_valid"),
        ),
        sa.CheckConstraint(
            "selected IS NULL OR char_length(selected) BETWEEN 1 AND 64",
            name=op.f("ck_companion_preference_selected_length"),
        ),
        sa.CheckConstraint(
            "(position_x IS NULL) = (position_y IS NULL)",
            name=op.f("ck_companion_preference_position_pair"),
        ),
        sa.CheckConstraint(
            "position_x IS NULL OR (position_x BETWEEN 0 AND 1 AND position_y BETWEEN 0 AND 1)",
            name=op.f("ck_companion_preference_position_range"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["app_user.id"],
            name=op.f("fk_companion_preference_user_id_app_user"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("user_id", name=op.f("pk_companion_preference")),
    )

    _secure("companion", "companion_id_seq")
    _secure("companion_frame", "companion_frame_id_seq")
    _secure("companion_preference", None)


def downgrade() -> None:
    op.drop_table("companion_preference")
    op.drop_index("ix_companion_frame_companion", table_name="companion_frame")
    op.drop_index("ix_companion_frame_owner_action", table_name="companion_frame")
    op.drop_table("companion_frame")
    op.drop_index("ix_companion_user_id", table_name="companion")
    op.drop_table("companion")
