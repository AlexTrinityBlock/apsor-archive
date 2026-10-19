"""ingest runtime config singleton

Revision ID: d4b8e6f1a2c7
Revises: d1e2f3a4b5c6
Create Date: 2026-10-19 18:30:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "d4b8e6f1a2c7"
down_revision: str | None = "d1e2f3a4b5c6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ingest_config",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column(
            "poll_seconds",
            sa.Float(),
            server_default=sa.text("1.0"),
            nullable=False,
        ),
        sa.Column(
            "extract_workers",
            sa.Integer(),
            server_default=sa.text("2"),
            nullable=False,
        ),
        sa.Column(
            "max_inflight_jobs",
            sa.Integer(),
            server_default=sa.text("2"),
            nullable=False,
        ),
        sa.Column(
            "embedding_concurrency",
            sa.Integer(),
            server_default=sa.text("6"),
            nullable=False,
        ),
        sa.Column(
            "chunk_target_chars",
            sa.Integer(),
            server_default=sa.text("4000"),
            nullable=False,
        ),
        sa.Column(
            "chunk_overlap_chars",
            sa.Integer(),
            server_default=sa.text("500"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("id = 1", name=op.f("ck_ingest_config_singleton")),
        sa.CheckConstraint(
            "poll_seconds BETWEEN 0.25 AND 30",
            name=op.f("ck_ingest_config_poll_seconds_range"),
        ),
        sa.CheckConstraint(
            "extract_workers BETWEEN 1 AND 8",
            name=op.f("ck_ingest_config_extract_workers_range"),
        ),
        sa.CheckConstraint(
            "max_inflight_jobs BETWEEN 1 AND 4",
            name=op.f("ck_ingest_config_max_inflight_jobs_range"),
        ),
        sa.CheckConstraint(
            "embedding_concurrency BETWEEN 1 AND 32",
            name=op.f("ck_ingest_config_embedding_concurrency_range"),
        ),
        sa.CheckConstraint(
            "chunk_target_chars BETWEEN 1000 AND 20000",
            name=op.f("ck_ingest_config_chunk_target_chars_range"),
        ),
        sa.CheckConstraint(
            "chunk_overlap_chars BETWEEN 0 AND 5000",
            name=op.f("ck_ingest_config_chunk_overlap_chars_range"),
        ),
        sa.CheckConstraint(
            "chunk_overlap_chars < chunk_target_chars",
            name=op.f("ck_ingest_config_overlap_below_target"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ingest_config")),
    )
    op.execute("INSERT INTO ingest_config (id) VALUES (1)")


def downgrade() -> None:
    op.drop_table("ingest_config")
