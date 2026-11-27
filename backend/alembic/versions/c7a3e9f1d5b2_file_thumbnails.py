"""tiny WebP thumbnails for file versions

Revision ID: c7a3e9f1d5b2
Revises: d8f2a6c4e1b9
Create Date: 2026-11-28 00:00:00.000000

Migration decisions:
- One row per file version, keyed by ``file_id``. A file id never changes its
  bytes (moves and renames keep the id, edits create a new id), so a thumbnail
  for an id is immutable and safe to cache for a long time.
- The WebP bytes (at most 32 KiB, usually under 10 KiB) live in PostgreSQL so
  chat and library cards never wait on an object-storage round trip, and a
  discarded staged file removes its thumbnail through ``ON DELETE CASCADE``.
- ``status`` records ``ready``, ``none`` (the format carries no visual), or
  ``failed`` so the backfill does not retry forever.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c7a3e9f1d5b2"
down_revision: str | None = "d8f2a6c4e1b9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "apsor_app"
TABLE = "file_thumbnail"


def upgrade() -> None:
    op.create_table(
        TABLE,
        sa.Column("file_id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("data", sa.LargeBinary(), nullable=True),
        sa.Column("width", sa.Integer(), nullable=True),
        sa.Column("height", sa.Integer(), nullable=True),
        sa.Column("sha256", sa.String(length=64), nullable=True),
        sa.Column("generator_version", sa.SmallInteger(), nullable=False),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column(
            "attempts",
            sa.SmallInteger(),
            server_default=sa.text("1"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('ready', 'none', 'failed')",
            name=op.f("ck_file_thumbnail_status_valid"),
        ),
        sa.CheckConstraint(
            "(status = 'ready') = (data IS NOT NULL) "
            "AND (status = 'ready') = (sha256 IS NOT NULL) "
            "AND (status = 'ready') = (width IS NOT NULL) "
            "AND (status = 'ready') = (height IS NOT NULL)",
            name=op.f("ck_file_thumbnail_ready_payload"),
        ),
        sa.CheckConstraint(
            "data IS NULL OR octet_length(data) <= 32768",
            name=op.f("ck_file_thumbnail_data_size"),
        ),
        sa.CheckConstraint(
            "width IS NULL OR (width BETWEEN 1 AND 512)",
            name=op.f("ck_file_thumbnail_width_range"),
        ),
        sa.CheckConstraint(
            "height IS NULL OR (height BETWEEN 1 AND 512)",
            name=op.f("ck_file_thumbnail_height_range"),
        ),
        sa.CheckConstraint(
            "sha256 IS NULL OR sha256 ~ '^[0-9a-f]{64}$'",
            name=op.f("ck_file_thumbnail_sha256_format"),
        ),
        sa.CheckConstraint(
            "attempts >= 1",
            name=op.f("ck_file_thumbnail_attempts_positive"),
        ),
        sa.ForeignKeyConstraint(
            ["file_id", "user_id"],
            ["file.id", "file.user_id"],
            name=op.f("fk_file_thumbnail_file_user"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["app_user.id"],
            name=op.f("fk_file_thumbnail_user_id_app_user"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("file_id", name=op.f("pk_file_thumbnail")),
    )
    op.create_index("ix_file_thumbnail_user_id", TABLE, ["user_id"], unique=False)

    op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {TABLE} TO {APP_ROLE}")
    op.execute(f"ALTER TABLE {TABLE} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {TABLE} FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY {TABLE}_owner ON {TABLE} "
        f"FOR ALL TO {APP_ROLE} "
        f"USING (user_id = nullif(current_setting('app.user_id', true), '')::bigint) "
        f"WITH CHECK (user_id = nullif(current_setting('app.user_id', true), '')::bigint)"
    )


def downgrade() -> None:
    op.drop_index("ix_file_thumbnail_user_id", table_name=TABLE)
    op.drop_table(TABLE)
