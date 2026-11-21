"""add granular ingestion stage progress

Revision ID: b3d7e9f1c2a4
Revises: c9e2f4a7b1d8
Create Date: 2026-11-21 12:00:00.000000

Adds nullable ``stage_done``, ``stage_total``, and ``stage_unit`` to the
durable job row. They describe the current extraction or chunking unit
(page, chunk, sheet, paragraph, image) while the job is parsing or chunking;
``progress_pct`` stays the coarse overall bar. All three are cleared when the
job moves to embedding, publication, failure, or a retry.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "b3d7e9f1c2a4"
down_revision: str | None = "c9e2f4a7b1d8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "file_ingest_job",
        sa.Column("stage_done", sa.Integer(), nullable=True),
    )
    op.add_column(
        "file_ingest_job",
        sa.Column("stage_total", sa.Integer(), nullable=True),
    )
    op.add_column(
        "file_ingest_job",
        sa.Column("stage_unit", sa.String(length=16), nullable=True),
    )
    op.create_check_constraint(
        op.f("ck_file_ingest_job_stage_done_non_negative"),
        "file_ingest_job",
        "stage_done IS NULL OR stage_done >= 0",
    )
    op.create_check_constraint(
        op.f("ck_file_ingest_job_stage_total_non_negative"),
        "file_ingest_job",
        "stage_total IS NULL OR stage_total >= 0",
    )
    op.create_check_constraint(
        op.f("ck_file_ingest_job_stage_done_within_total"),
        "file_ingest_job",
        "stage_done IS NULL OR stage_total IS NULL OR stage_done <= stage_total",
    )
    op.create_check_constraint(
        op.f("ck_file_ingest_job_stage_unit_length"),
        "file_ingest_job",
        "stage_unit IS NULL OR (char_length(stage_unit) >= 1 "
        "AND char_length(stage_unit) <= 16)",
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("ck_file_ingest_job_stage_unit_length"),
        "file_ingest_job",
        type_="check",
    )
    op.drop_constraint(
        op.f("ck_file_ingest_job_stage_done_within_total"),
        "file_ingest_job",
        type_="check",
    )
    op.drop_constraint(
        op.f("ck_file_ingest_job_stage_total_non_negative"),
        "file_ingest_job",
        type_="check",
    )
    op.drop_constraint(
        op.f("ck_file_ingest_job_stage_done_non_negative"),
        "file_ingest_job",
        type_="check",
    )
    op.drop_column("file_ingest_job", "stage_unit")
    op.drop_column("file_ingest_job", "stage_total")
    op.drop_column("file_ingest_job", "stage_done")
