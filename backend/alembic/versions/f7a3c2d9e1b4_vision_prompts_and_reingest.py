"""configurable vision prompts and vision re-ingest

Revision ID: f7a3c2d9e1b4
Revises: c2f6a8d4e1b3
Create Date: 2026-11-06 00:00:00.000000

Adds the two editable vision prompt templates, the per-file extraction
fingerprint, and the re-ingest source pointer. Prompt columns stay nullable so
``NULL`` means "use the built-in default"; file fingerprint columns stay
nullable so legacy extractions are not backfilled with synthetic values.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import context, op

revision: str = "f7a3c2d9e1b4"
down_revision: str | None = "c2f6a8d4e1b3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_INGEST_ACTIVE_STATUS_SQL = (
    "status IN ('queued', 'parsing', 'chunking', 'embedding', 'summarizing')"
)


def upgrade() -> None:
    """Add prompt templates, extraction fingerprints, and re-ingest linkage."""
    op.add_column(
        "ingest_config",
        sa.Column("vision_image_prompt", sa.Text(), nullable=True),
    )
    op.add_column(
        "ingest_config",
        sa.Column("vision_document_prompt", sa.Text(), nullable=True),
    )
    op.create_check_constraint(
        op.f("ck_ingest_config_vision_image_prompt_length"),
        "ingest_config",
        "vision_image_prompt IS NULL "
        "OR char_length(btrim(vision_image_prompt)) BETWEEN 1 AND 32000",
    )
    op.create_check_constraint(
        op.f("ck_ingest_config_vision_document_prompt_length"),
        "ingest_config",
        "vision_document_prompt IS NULL "
        "OR char_length(btrim(vision_document_prompt)) BETWEEN 1 AND 32000",
    )

    op.add_column("file", sa.Column("vision_prompt_sha256", sa.String(length=64), nullable=True))
    op.add_column("file", sa.Column("vision_prompt_mode", sa.String(length=16), nullable=True))
    op.add_column(
        "file",
        sa.Column("vision_description_language", sa.String(length=80), nullable=True),
    )
    op.create_check_constraint(
        op.f("ck_file_vision_prompt_pair"),
        "file",
        "(vision_prompt_sha256 IS NULL) = (vision_prompt_mode IS NULL)",
    )
    op.create_check_constraint(
        op.f("ck_file_vision_prompt_mode_valid"),
        "file",
        "vision_prompt_mode IS NULL OR vision_prompt_mode IN ('image', 'document')",
    )
    op.create_check_constraint(
        op.f("ck_file_vision_prompt_sha256_format"),
        "file",
        "vision_prompt_sha256 IS NULL OR vision_prompt_sha256 ~ '^[0-9a-f]{64}$'",
    )
    op.create_check_constraint(
        op.f("ck_file_vision_description_language_length"),
        "file",
        "vision_description_language IS NULL "
        "OR char_length(btrim(vision_description_language)) BETWEEN 1 AND 80",
    )

    op.add_column(
        "file_ingest_job",
        sa.Column("source_file_id", sa.BigInteger(), nullable=True),
    )
    unexpected_sources: list[str] = []
    if not context.is_offline_mode():
        unexpected_sources = list(
            op.get_bind()
            .execute(
                sa.text(
                    "SELECT DISTINCT source_kind FROM file_ingest_job "
                    "WHERE source_kind NOT IN ('upload', 'text')"
                )
            )
            .scalars()
            .all()
        )
    if unexpected_sources:
        raise RuntimeError(
            "Cannot add the re-ingest source check: unexpected file_ingest_job "
            f"source_kind values {sorted(unexpected_sources)!r}."
        )
    op.drop_constraint(
        op.f("ck_file_ingest_job_source_kind_valid"),
        "file_ingest_job",
        type_="check",
    )
    op.create_check_constraint(
        op.f("ck_file_ingest_job_source_kind_valid"),
        "file_ingest_job",
        "source_kind IN ('upload', 'text', 'reingest')",
    )
    op.create_foreign_key(
        op.f("fk_file_ingest_job_source_file_user"),
        "file_ingest_job",
        "file",
        ["source_file_id", "user_id"],
        ["id", "user_id"],
        ondelete="RESTRICT",
    )
    op.create_check_constraint(
        op.f("ck_file_ingest_job_reingest_source"),
        "file_ingest_job",
        "source_kind <> 'reingest' OR (source_file_id IS NOT NULL "
        "AND storage_key IS NULL AND storage_backend IS NULL)",
    )
    op.create_index(
        "uq_file_ingest_job_source_file_active",
        "file_ingest_job",
        ["user_id", "source_file_id"],
        unique=True,
        postgresql_where=sa.text(
            "source_kind = 'reingest' AND " + _INGEST_ACTIVE_STATUS_SQL
        ),
    )
    op.create_index(
        "ix_file_ingest_job_user_id_source_file",
        "file_ingest_job",
        ["user_id", "source_file_id"],
    )


def downgrade() -> None:
    """Remove re-ingest jobs first, then unwind the new columns and checks."""
    op.execute("DELETE FROM file_ingest_job WHERE source_kind = 'reingest'")

    op.drop_index(
        "ix_file_ingest_job_user_id_source_file",
        table_name="file_ingest_job",
    )
    op.drop_index(
        "uq_file_ingest_job_source_file_active",
        table_name="file_ingest_job",
    )
    op.drop_constraint(
        op.f("ck_file_ingest_job_reingest_source"),
        "file_ingest_job",
        type_="check",
    )
    op.drop_constraint(
        op.f("fk_file_ingest_job_source_file_user"),
        "file_ingest_job",
        type_="foreignkey",
    )
    op.drop_constraint(
        op.f("ck_file_ingest_job_source_kind_valid"),
        "file_ingest_job",
        type_="check",
    )
    op.create_check_constraint(
        op.f("ck_file_ingest_job_source_kind_valid"),
        "file_ingest_job",
        "source_kind IN ('upload', 'text')",
    )
    op.drop_column("file_ingest_job", "source_file_id")

    op.drop_constraint(
        op.f("ck_file_vision_description_language_length"),
        "file",
        type_="check",
    )
    op.drop_constraint(
        op.f("ck_file_vision_prompt_sha256_format"),
        "file",
        type_="check",
    )
    op.drop_constraint(
        op.f("ck_file_vision_prompt_mode_valid"),
        "file",
        type_="check",
    )
    op.drop_constraint(
        op.f("ck_file_vision_prompt_pair"),
        "file",
        type_="check",
    )
    op.drop_column("file", "vision_description_language")
    op.drop_column("file", "vision_prompt_mode")
    op.drop_column("file", "vision_prompt_sha256")

    op.drop_constraint(
        op.f("ck_ingest_config_vision_document_prompt_length"),
        "ingest_config",
        type_="check",
    )
    op.drop_constraint(
        op.f("ck_ingest_config_vision_image_prompt_length"),
        "ingest_config",
        type_="check",
    )
    op.drop_column("ingest_config", "vision_document_prompt")
    op.drop_column("ingest_config", "vision_image_prompt")
