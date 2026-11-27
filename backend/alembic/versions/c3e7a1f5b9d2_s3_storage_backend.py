"""allow the generic s3 storage backend

Revision ID: c3e7a1f5b9d2
Revises: d8f2a6c4e1b9
Create Date: 2026-11-28 10:00:00.000000

Migration decisions:
- Original bytes can now live in any S3-compatible bucket (the bundled RustFS
  service, AWS S3, MinIO) in addition to local disk and Cloudflare R2. Rows
  record the canonical name ``s3``; ``rustfs`` is only a configuration alias.
- ``r2`` stays a distinct value, so existing R2 rows keep resolving to the R2
  adapter and a staged R2-to-RustFS move can serve a mixed archive.
- Downgrade restores the two-value checks. It fails while any row still
  records ``s3``; move those objects back to local or R2 first.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "c3e7a1f5b9d2"
down_revision: str | None = "d8f2a6c4e1b9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLES = ("file", "file_ingest_job", "agent_chat_attachment")


def _replace_check(table: str, values: str) -> None:
    name = op.f(f"ck_{table}_storage_backend_valid")
    op.drop_constraint(name, table, type_="check")
    op.create_check_constraint(name, table, f"storage_backend IN ({values})")


def upgrade() -> None:
    """Accept ``s3`` as a persisted storage backend."""
    for table in _TABLES:
        _replace_check(table, "'local', 'r2', 's3'")


def downgrade() -> None:
    """Restore the local/R2-only checks."""
    for table in _TABLES:
        _replace_check(table, "'local', 'r2'")
