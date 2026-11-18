"""ordered provider chains and persistent provider-error notices

Revision ID: d9b3e7f1c5a2
Revises: c4f8a2d6e9b1
Create Date: 2026-11-18 12:00:00.000000

Each capability table gains a zero-based ``priority``. ``is_active`` keeps its
meaning but now means "member of the chain": several active rows are allowed as
long as their priorities are distinct. The old partial unique index on
``is_active`` is replaced by a partial unique index on ``priority WHERE
is_active``. Existing active rows are backfilled to priority 0; only one active
row per table can exist before this revision, so the new index is safe.

The downgrade first deactivates every active row except the lowest-priority one
in each table, then restores the single-active-row index. A downgrade must never
fail merely because an operator configured backups.

A global ``provider_error_notice`` table records sanitized whole-chain failures
for root. It follows the existing global-table RLS shape: read-all and
root-write, with explicit grants for ``apsor_app``.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "d9b3e7f1c5a2"
down_revision: str | None = "c4f8a2d6e9b1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "apsor_app"
_TABLES = (
    "chat_provider_config",
    "embedding_provider_config",
    "web_search_provider_config",
    "web_fetch_provider_config",
)
_NOTICE_TABLE = "provider_error_notice"
_NOTICE_SEQUENCE = "provider_error_notice_id_seq"


def _add_priority_columns() -> None:
    for table_name in _TABLES:
        op.add_column(
            table_name,
            sa.Column(
                "priority",
                sa.Integer(),
                server_default=sa.text("0"),
                nullable=False,
            ),
        )
        op.create_check_constraint(
            op.f(f"ck_{table_name}_priority_non_negative"),
            table_name,
            "priority >= 0",
        )
        # Existing rows all receive the server default 0. Inactive rows may
        # share a priority because the new index is partial.
        op.execute(f"UPDATE {table_name} SET priority = 0")
        op.drop_index(f"uq_{table_name}_active", table_name=table_name)
        op.create_index(
            f"uq_{table_name}_active_priority",
            table_name,
            ["priority"],
            unique=True,
            postgresql_where=sa.text("is_active"),
        )


def _drop_priority_columns() -> None:
    for table_name in _TABLES:
        # A chain must collapse to exactly one active row before the
        # single-active-row index returns. Keep the primary; deactivate backups.
        op.execute(
            f"""
            UPDATE {table_name}
            SET is_active = false, updated_at = now()
            WHERE is_active
              AND id <> (
                  SELECT id FROM {table_name} AS primary_row
                  WHERE primary_row.is_active
                  ORDER BY primary_row.priority, primary_row.id
                  LIMIT 1
              )
            """
        )
        op.drop_index(
            f"uq_{table_name}_active_priority",
            table_name=table_name,
        )
        op.create_index(
            f"uq_{table_name}_active",
            table_name,
            ["is_active"],
            unique=True,
            postgresql_where=sa.text("is_active"),
        )
        op.drop_constraint(
            op.f(f"ck_{table_name}_priority_non_negative"),
            table_name,
            type_="check",
        )
        op.drop_column(table_name, "priority")


def _create_notice_table() -> None:
    op.create_table(
        _NOTICE_TABLE,
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("capability", sa.String(length=32), nullable=False),
        sa.Column("operation", sa.String(length=32), nullable=False),
        sa.Column("error_code", sa.String(length=64), nullable=False),
        sa.Column("status_code", sa.Integer(), nullable=True),
        sa.Column("detail", sa.Text(), nullable=False),
        sa.Column(
            "attempts",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "count",
            sa.BigInteger(),
            server_default=sa.text("1"),
            nullable=False,
        ),
        sa.Column(
            "first_seen_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "last_seen_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_by_user_id", sa.BigInteger(), nullable=True),
        sa.CheckConstraint(
            "capability IN ('chat', 'embedding', 'web_search', 'web_fetch')",
            name=op.f("ck_provider_error_notice_capability_valid"),
        ),
        sa.CheckConstraint(
            "count >= 0",
            name=op.f("ck_provider_error_notice_count_non_negative"),
        ),
        sa.ForeignKeyConstraint(
            ["resolved_by_user_id"],
            ["app_user.id"],
            name=op.f("fk_provider_error_notice_resolved_by_user_id_app_user"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_provider_error_notice")),
    )
    op.create_index(
        "ix_provider_error_notice_resolved_last_seen",
        _NOTICE_TABLE,
        ["resolved_at", "last_seen_at"],
    )

    op.execute(
        f"GRANT SELECT, INSERT, UPDATE, DELETE ON {_NOTICE_TABLE} TO {APP_ROLE}"
    )
    op.execute(f"GRANT USAGE, SELECT ON SEQUENCE {_NOTICE_SEQUENCE} TO {APP_ROLE}")
    op.execute(f"ALTER TABLE {_NOTICE_TABLE} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {_NOTICE_TABLE} FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY {_NOTICE_TABLE}_read ON {_NOTICE_TABLE} "
        f"FOR SELECT TO {APP_ROLE} USING (true)"
    )
    op.execute(
        f"CREATE POLICY {_NOTICE_TABLE}_root_write ON {_NOTICE_TABLE} "
        f"FOR ALL TO {APP_ROLE} "
        f"USING (current_setting('app.user_role', true) = 'root') "
        f"WITH CHECK (current_setting('app.user_role', true) = 'root')"
    )


def _drop_notice_table() -> None:
    op.drop_index(
        "ix_provider_error_notice_resolved_last_seen",
        table_name=_NOTICE_TABLE,
    )
    op.drop_table(_NOTICE_TABLE)


def upgrade() -> None:
    _add_priority_columns()
    _create_notice_table()


def downgrade() -> None:
    _drop_notice_table()
    _drop_priority_columns()
