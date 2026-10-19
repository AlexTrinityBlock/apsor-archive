"""durable file ingestion jobs

Revision ID: d1e2f3a4b5c6
Revises: c9f1a2b3d4e5
Create Date: 2026-10-19 18:30:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "d1e2f3a4b5c6"
down_revision: str | None = "c9f1a2b3d4e5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_ACTIVE_STATUS_SQL = (
    "status IN ('queued', 'parsing', 'chunking', 'embedding', 'summarizing')"
)


def upgrade() -> None:
    """Create the job queue, progress ledger, and crash-recovery table."""
    op.create_table(
        "file_ingest_job",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("file_id", sa.BigInteger(), nullable=True),
        sa.Column("source_kind", sa.String(length=16), nullable=False),
        sa.Column("path", sa.Text(), nullable=False),
        sa.Column("storage_key", sa.Text(), nullable=True),
        sa.Column("mime_type", sa.String(length=255), nullable=False),
        sa.Column("file_name", sa.Text(), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "status",
            sa.String(length=16),
            server_default=sa.text("'queued'"),
            nullable=False,
        ),
        sa.Column("stage", sa.Text(), nullable=True),
        sa.Column(
            "progress_pct",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column("chunks_total", sa.Integer(), nullable=True),
        sa.Column("chunks_embedded", sa.Integer(), nullable=True),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("error_detail", sa.Text(), nullable=True),
        sa.Column(
            "attempts",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
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
            "source_kind IN ('upload', 'text')",
            name=op.f("ck_file_ingest_job_source_kind_valid"),
        ),
        sa.CheckConstraint(
            "status IN ('queued', 'parsing', 'chunking', 'embedding', "
            "'summarizing', 'ready', 'failed')",
            name=op.f("ck_file_ingest_job_status_valid"),
        ),
        sa.CheckConstraint(
            "progress_pct >= 0 AND progress_pct <= 100",
            name=op.f("ck_file_ingest_job_progress_pct_range"),
        ),
        sa.CheckConstraint(
            "chunks_total IS NULL OR chunks_total >= 0",
            name=op.f("ck_file_ingest_job_chunks_total_non_negative"),
        ),
        sa.CheckConstraint(
            "chunks_embedded IS NULL OR chunks_embedded >= 0",
            name=op.f("ck_file_ingest_job_chunks_embedded_non_negative"),
        ),
        sa.CheckConstraint(
            "attempts >= 0",
            name=op.f("ck_file_ingest_job_attempts_non_negative"),
        ),
        sa.CheckConstraint(
            "size_bytes >= 0",
            name=op.f("ck_file_ingest_job_size_non_negative"),
        ),
        sa.ForeignKeyConstraint(
            ["file_id"],
            ["file.id"],
            name=op.f("fk_file_ingest_job_file_id_file"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_file_ingest_job")),
    )
    op.create_index(
        "uq_file_ingest_job_active_path",
        "file_ingest_job",
        ["path"],
        unique=True,
        postgresql_where=sa.text(_ACTIVE_STATUS_SQL),
    )
    op.create_index(
        "uq_file_ingest_job_file_id",
        "file_ingest_job",
        ["file_id"],
        unique=True,
        postgresql_where=sa.text("file_id IS NOT NULL"),
    )
    op.create_index(
        "ix_file_ingest_job_status_created",
        "file_ingest_job",
        ["status", "created_at"],
    )
    op.create_index(
        "ix_file_ingest_job_updated_at",
        "file_ingest_job",
        ["updated_at"],
    )


def downgrade() -> None:
    """Drop the ingestion queue and its progress history."""
    op.drop_index("ix_file_ingest_job_updated_at", table_name="file_ingest_job")
    op.drop_index("ix_file_ingest_job_status_created", table_name="file_ingest_job")
    op.drop_index("uq_file_ingest_job_file_id", table_name="file_ingest_job")
    op.drop_index("uq_file_ingest_job_active_path", table_name="file_ingest_job")
    op.drop_table("file_ingest_job")
