"""multi-user ownership, composite lineage FKs, and row-level security

Revision ID: e8f1c4d2a7b9
Revises: b8f4c2d9e6a1
Create Date: 2026-10-25 00:00:00.000000

Every private archive row gains an owner (``user_id``) and every parent/child
relationship becomes a composite foreign key on ``(id, user_id)`` so a row can
never point at another user's lineage. Existing rows are assigned to the oldest
``app_user``, which also becomes the single ``root`` account.

The migration then creates the non-login ``apsor_app`` role, grants the runtime
privileges it needs, and enables forced row-level security on every private
table and every global configuration table. ``app_user`` and ``user_session``
deliberately stay outside RLS because authentication runs before a user context
exists.

Composite ``ON DELETE SET NULL`` actions use PostgreSQL's column-list form
(``SET NULL (column)``) so only the nullable lineage column is cleared and the
``user_id`` owner is preserved. This keeps the original cascade/restrict/set-null
behavior of every relationship.

Two operational details are intentional:

* A database built entirely from the migration chain has no account yet but
  contains the three legacy prompt seeds. Because those rows cannot have an
  owner, they are removed when ``app_user`` is empty; first-run setup creates
  the root account with an empty personal prompt list. If any other private
  row exists without an account, the upgrade raises a clear error.
* ``apsor_app`` is a cluster-wide role. New tables get no default DML grant;
  each migration must grant and add RLS explicitly. The downgrade revokes this
  database's grants but does not drop the role, because another database (for
  example a test database) may still reference it.
* ``alembic_version`` is explicitly excluded from the runtime grants so the
  application role cannot rewrite migration history; Alembic itself continues
  to run as the owning login.
"""

from collections.abc import Sequence
from typing import NamedTuple

import sqlalchemy as sa

from alembic import op

revision: str = "e8f1c4d2a7b9"
down_revision: str | None = "b8f4c2d9e6a1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "apsor_app"

# Tables that gain an owner column in this revision. ``user_profile_card`` is
# private too, but it already had ``user_id``.
_USER_ID_TABLES: tuple[str, ...] = (
    "file",
    "folder",
    "chunk",
    "chunk_ngram",
    "memory",
    "memory_summary",
    "file_ingest_job",
    "agent_conversation",
    "agent_entry",
    "agent_run",
    "agent_approval",
    "saved_question",
    "frequently_used_prompt",
)

_PRIVATE_TABLES: tuple[str, ...] = (*_USER_ID_TABLES, "user_profile_card")

_GLOBAL_TABLES: tuple[str, ...] = (
    "ingest_config",
    "agent_config",
    "system_prompt_section",
    "chat_provider_config",
    "embedding_provider_config",
    "web_search_provider_config",
    "web_fetch_provider_config",
)

# Parent tables referenced by composite ``(child_column, user_id)`` foreign keys.
_UNIQUE_ID_USER_TABLES: tuple[str, ...] = (
    "file",
    "folder",
    "chunk",
    "memory",
    "agent_conversation",
    "agent_entry",
    "agent_run",
)

_COUNT_PRIVATE_ROWS_SQL = """
SELECT
    (SELECT count(*) FROM file)
  + (SELECT count(*) FROM folder)
  + (SELECT count(*) FROM chunk)
  + (SELECT count(*) FROM chunk_ngram)
  + (SELECT count(*) FROM memory)
  + (SELECT count(*) FROM memory_summary)
  + (SELECT count(*) FROM file_ingest_job)
  + (SELECT count(*) FROM agent_conversation)
  + (SELECT count(*) FROM agent_entry)
  + (SELECT count(*) FROM agent_run)
  + (SELECT count(*) FROM agent_approval)
  + (SELECT count(*) FROM saved_question)
  + (SELECT count(*) FROM frequently_used_prompt)
"""

_FILE_CURRENT_PATH_WHERE = "is_current AND deleted_at IS NULL"
_INGEST_ACTIVE_PATH_WHERE = (
    "status IN ('queued', 'parsing', 'chunking', 'embedding', 'summarizing')"
)
_CHUNK_CURRENT_WHERE = "is_current"
_MEMORY_ACTIVE_WHERE = "deleted_at IS NULL"


class _CompositeForeignKey(NamedTuple):
    """One composite owner-safe replacement for an existing single-column FK."""

    name: str
    old_name: str
    table: str
    columns: tuple[str, ...]
    referred_table: str
    referred_columns: tuple[str, ...]
    ondelete: str
    old_ondelete: str


_COMPOSITE_FKS: tuple[_CompositeForeignKey, ...] = (
    _CompositeForeignKey(
        "fk_file_supersedes_user",
        "fk_file_supersedes_file_id_file",
        "file",
        ("supersedes_file_id", "user_id"),
        "file",
        ("id", "user_id"),
        "SET NULL (supersedes_file_id)",
        "SET NULL",
    ),
    _CompositeForeignKey(
        "fk_folder_parent_user",
        "fk_folder_parent_id_folder",
        "folder",
        ("parent_id", "user_id"),
        "folder",
        ("id", "user_id"),
        "CASCADE",
        "CASCADE",
    ),
    _CompositeForeignKey(
        "fk_memory_superseded_by_user",
        "fk_memory_superseded_by_id_memory",
        "memory",
        ("superseded_by_id", "user_id"),
        "memory",
        ("id", "user_id"),
        "SET NULL (superseded_by_id)",
        "SET NULL",
    ),
    _CompositeForeignKey(
        "fk_chunk_ngram_chunk_user",
        "fk_chunk_ngram_chunk_id_chunk",
        "chunk_ngram",
        ("chunk_id", "user_id"),
        "chunk",
        ("id", "user_id"),
        "CASCADE",
        "CASCADE",
    ),
    _CompositeForeignKey(
        "fk_file_ingest_job_file_user",
        "fk_file_ingest_job_file_id_file",
        "file_ingest_job",
        ("file_id", "user_id"),
        "file",
        ("id", "user_id"),
        "CASCADE",
        "CASCADE",
    ),
    _CompositeForeignKey(
        "fk_agent_conversation_parent_user",
        "fk_agent_conversation_parent_conversation_id_agent_conversation",
        "agent_conversation",
        ("parent_conversation_id", "user_id"),
        "agent_conversation",
        ("id", "user_id"),
        "SET NULL (parent_conversation_id)",
        "SET NULL",
    ),
    _CompositeForeignKey(
        "fk_agent_conversation_fork_entry_user",
        "fk_agent_conversation_fork_at_entry_id_agent_entry",
        "agent_conversation",
        ("fork_at_entry_id", "user_id"),
        "agent_entry",
        ("id", "user_id"),
        "SET NULL (fork_at_entry_id)",
        "SET NULL",
    ),
    _CompositeForeignKey(
        "fk_agent_entry_conversation_user",
        "fk_agent_entry_conversation_id_agent_conversation",
        "agent_entry",
        ("conversation_id", "user_id"),
        "agent_conversation",
        ("id", "user_id"),
        "CASCADE",
        "CASCADE",
    ),
    _CompositeForeignKey(
        "fk_agent_entry_head_user",
        "fk_agent_entry_head_entry_id_agent_entry",
        "agent_entry",
        ("head_entry_id", "user_id"),
        "agent_entry",
        ("id", "user_id"),
        "SET NULL (head_entry_id)",
        "SET NULL",
    ),
    _CompositeForeignKey(
        "fk_agent_entry_run_user",
        "fk_agent_entry_by_run_id_agent_run",
        "agent_entry",
        ("by_run_id", "user_id"),
        "agent_run",
        ("id", "user_id"),
        "SET NULL (by_run_id)",
        "SET NULL",
    ),
    _CompositeForeignKey(
        "fk_agent_run_conversation_user",
        "fk_agent_run_conversation_id_agent_conversation",
        "agent_run",
        ("conversation_id", "user_id"),
        "agent_conversation",
        ("id", "user_id"),
        "CASCADE",
        "CASCADE",
    ),
    _CompositeForeignKey(
        "fk_agent_run_last_entry_user",
        "fk_agent_run_last_entry_id_agent_entry",
        "agent_run",
        ("last_entry_id", "user_id"),
        "agent_entry",
        ("id", "user_id"),
        "SET NULL (last_entry_id)",
        "SET NULL",
    ),
    _CompositeForeignKey(
        "fk_agent_run_user_entry_user",
        "fk_agent_run_user_entry_id_agent_entry",
        "agent_run",
        ("user_entry_id", "user_id"),
        "agent_entry",
        ("id", "user_id"),
        "RESTRICT",
        "RESTRICT",
    ),
    _CompositeForeignKey(
        "fk_agent_approval_conversation_user",
        "fk_agent_approval_conversation_id_agent_conversation",
        "agent_approval",
        ("conversation_id", "user_id"),
        "agent_conversation",
        ("id", "user_id"),
        "CASCADE",
        "CASCADE",
    ),
    _CompositeForeignKey(
        "fk_agent_approval_run_user",
        "fk_agent_approval_run_id_agent_run",
        "agent_approval",
        ("run_id", "user_id"),
        "agent_run",
        ("id", "user_id"),
        "CASCADE",
        "CASCADE",
    ),
    _CompositeForeignKey(
        "fk_agent_approval_resolved_entry_user",
        "fk_agent_approval_resolved_by_entry_id_agent_entry",
        "agent_approval",
        ("resolved_by_entry_id", "user_id"),
        "agent_entry",
        ("id", "user_id"),
        "SET NULL (resolved_by_entry_id)",
        "SET NULL",
    ),
    _CompositeForeignKey(
        "fk_saved_question_conversation_user",
        "fk_saved_question_conversation_id_agent_conversation",
        "saved_question",
        ("conversation_id", "user_id"),
        "agent_conversation",
        ("id", "user_id"),
        "SET NULL (conversation_id)",
        "SET NULL",
    ),
)


def _user_id_fk_name(table: str) -> str:
    return f"fk_{table}_user_id_app_user"


def _add_app_user_columns() -> None:
    op.add_column(
        "app_user",
        sa.Column("role", sa.String(length=16), nullable=False, server_default=sa.text("'user'")),
    )
    op.add_column(
        "app_user",
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
    )
    op.add_column(
        "app_user",
        sa.Column(
            "must_change_password",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "app_user",
        sa.Column("password_changed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "app_user",
        sa.Column("created_by_user_id", sa.BigInteger(), nullable=True),
    )
    op.add_column(
        "app_user",
        sa.Column("disabled_at", sa.DateTime(timezone=True), nullable=True),
    )


def _add_ownership_columns() -> None:
    for table in _USER_ID_TABLES:
        op.add_column(table, sa.Column("user_id", sa.BigInteger(), nullable=True))


def _add_storage_backend_columns() -> None:
    op.add_column("file", sa.Column("storage_backend", sa.String(length=16), nullable=True))
    op.add_column(
        "file_ingest_job",
        sa.Column("storage_backend", sa.String(length=16), nullable=True),
    )


def _backfill_existing_rows() -> None:
    bind = op.get_bind()
    owner_id = bind.execute(sa.text("SELECT id FROM app_user ORDER BY id LIMIT 1")).scalar()
    if owner_id is None:
        # A database built entirely from the migration chain has no account yet
        # but does contain the three legacy prompt shortcuts seeded by the
        # frequent-prompts migration. They have no possible owner, so drop them;
        # first-run setup creates the root account with an empty personal list.
        bind.execute(sa.text("DELETE FROM frequently_used_prompt"))
        private_rows = bind.execute(sa.text(_COUNT_PRIVATE_ROWS_SQL)).scalar_one()
        if private_rows:
            raise RuntimeError(
                "Cannot add multi-user ownership: private archive rows exist but "
                "app_user is empty. Create the bootstrap account before upgrading."
            )
        return

    for table in _USER_ID_TABLES:
        bind.execute(
            sa.text(f"UPDATE {table} SET user_id = :owner_id WHERE user_id IS NULL"),
            {"owner_id": owner_id},
        )
    bind.execute(
        sa.text(
            "UPDATE app_user "
            "SET role = 'root', is_active = true, disabled_at = NULL "
            "WHERE id = :owner_id"
        ),
        {"owner_id": owner_id},
    )
    bind.execute(
        sa.text(
            "UPDATE file SET storage_backend = 'local' "
            "WHERE storage_key IS NOT NULL AND storage_backend IS NULL"
        )
    )
    bind.execute(
        sa.text(
            "UPDATE file_ingest_job SET storage_backend = 'local' "
            "WHERE storage_key IS NOT NULL AND storage_backend IS NULL"
        )
    )


def _enforce_ownership() -> None:
    for table in _USER_ID_TABLES:
        op.alter_column(
            table,
            "user_id",
            existing_type=sa.BigInteger(),
            nullable=False,
        )
        op.create_foreign_key(
            _user_id_fk_name(table),
            table,
            "app_user",
            ["user_id"],
            ["id"],
            ondelete="RESTRICT",
        )
    for table in _UNIQUE_ID_USER_TABLES:
        op.create_unique_constraint(
            f"uq_{table}_id_user_id",
            table,
            ["id", "user_id"],
        )


def _replace_foreign_keys() -> None:
    for fk in _COMPOSITE_FKS:
        op.drop_constraint(fk.old_name, fk.table, type_="foreignkey")
        op.create_foreign_key(
            fk.name,
            fk.table,
            fk.referred_table,
            list(fk.columns),
            list(fk.referred_columns),
            ondelete=fk.ondelete,
        )


def _replace_indexes() -> None:
    op.drop_index("uq_file_current_path", table_name="file")
    op.create_index(
        "uq_file_current_path",
        "file",
        ["user_id", "raw_file_path"],
        unique=True,
        postgresql_where=sa.text(_FILE_CURRENT_PATH_WHERE),
    )
    op.create_index("ix_file_user_id_updated_at", "file", ["user_id", "updated_at"])

    op.drop_index("uq_folder_path", table_name="folder")
    op.create_index("uq_folder_path", "folder", ["user_id", "path"], unique=True)
    op.create_index("ix_folder_user_id_parent_id", "folder", ["user_id", "parent_id"])
    op.create_index("ix_folder_user_id_depth", "folder", ["user_id", "depth"])

    op.drop_index("uq_chunk_current_source_ordinal", table_name="chunk")
    op.create_index(
        "uq_chunk_current_source_ordinal",
        "chunk",
        ["user_id", "source_kind", "source_id", "chunk_index"],
        unique=True,
        postgresql_where=sa.text(_CHUNK_CURRENT_WHERE),
    )
    op.create_index(
        "ix_chunk_user_id_source",
        "chunk",
        ["user_id", "source_kind", "source_id"],
    )
    op.create_index("ix_chunk_user_id_current", "chunk", ["user_id", "is_current"])
    op.create_index("ix_chunk_ngram_user_id_gram", "chunk_ngram", ["user_id", "gram"])

    op.create_index(
        "ix_memory_user_id_time_active",
        "memory",
        ["user_id", "memory_time"],
        postgresql_where=sa.text(_MEMORY_ACTIVE_WHERE),
    )
    op.create_index(
        "ix_memory_summary_user_id_period_end",
        "memory_summary",
        ["user_id", "period_end"],
    )

    op.drop_index("uq_file_ingest_job_active_path", table_name="file_ingest_job")
    op.create_index(
        "uq_file_ingest_job_active_path",
        "file_ingest_job",
        ["user_id", "path"],
        unique=True,
        postgresql_where=sa.text(_INGEST_ACTIVE_PATH_WHERE),
    )
    op.create_index(
        "ix_file_ingest_job_user_id_status_created",
        "file_ingest_job",
        ["user_id", "status", "created_at"],
    )

    op.drop_constraint(
        "uq_agent_conversation_provider_session_id",
        "agent_conversation",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_agent_conversation_provider_session_id",
        "agent_conversation",
        ["user_id", "provider_session_id"],
    )
    op.create_index(
        "ix_agent_conversation_user_id_last_entry_at",
        "agent_conversation",
        ["user_id", "last_entry_at"],
    )
    op.create_index(
        "ix_agent_conversation_user_id_status",
        "agent_conversation",
        ["user_id", "status"],
    )
    op.create_index(
        "ix_agent_entry_user_id_conversation_id",
        "agent_entry",
        ["user_id", "conversation_id", "id"],
    )
    op.create_index(
        "ix_agent_run_user_id_conversation_id",
        "agent_run",
        ["user_id", "conversation_id", "id"],
    )
    op.create_index(
        "ix_agent_run_user_id_conversation_status",
        "agent_run",
        ["user_id", "conversation_id", "status"],
    )
    op.create_index(
        "ix_agent_approval_user_id_conversation_status",
        "agent_approval",
        ["user_id", "conversation_id", "status"],
    )
    op.create_index(
        "ix_saved_question_user_id_conversation_id",
        "saved_question",
        ["user_id", "conversation_id"],
    )
    op.create_index(
        "ix_frequently_used_prompt_user_id_order",
        "frequently_used_prompt",
        ["user_id", "sort_order", "id"],
    )


def _add_storage_constraints() -> None:
    op.create_check_constraint(
        op.f("ck_file_storage_backend_valid"),
        "file",
        "storage_backend IN ('local', 'r2')",
    )
    op.create_check_constraint(
        op.f("ck_file_storage_backend_key_pair"),
        "file",
        "(storage_key IS NULL) = (storage_backend IS NULL)",
    )
    op.create_check_constraint(
        op.f("ck_file_ingest_job_storage_backend_valid"),
        "file_ingest_job",
        "storage_backend IN ('local', 'r2')",
    )
    op.create_check_constraint(
        op.f("ck_file_ingest_job_storage_backend_key_pair"),
        "file_ingest_job",
        "(storage_key IS NULL) = (storage_backend IS NULL)",
    )


def _add_app_user_constraints() -> None:
    op.create_check_constraint(
        op.f("ck_app_user_role_valid"),
        "app_user",
        "role IN ('root', 'user')",
    )
    op.create_check_constraint(
        op.f("ck_app_user_active_disabled"),
        "app_user",
        "(is_active AND disabled_at IS NULL) OR (NOT is_active AND disabled_at IS NOT NULL)",
    )
    op.create_foreign_key(
        "fk_app_user_created_by_user_id_app_user",
        "app_user",
        "app_user",
        ["created_by_user_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index(
        "uq_app_user_single_root",
        "app_user",
        ["role"],
        unique=True,
        postgresql_where=sa.text("role = 'root'"),
    )


def _enable_rls() -> None:
    op.execute(
        f"""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{APP_ROLE}') THEN
                EXECUTE 'CREATE ROLE {APP_ROLE} NOLOGIN';
            END IF;
        END
        $$;
        """
    )
    op.execute(f"GRANT USAGE ON SCHEMA public TO {APP_ROLE}")
    op.execute(
        f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {APP_ROLE}"
    )
    # Alembic's bookkeeping table is owned by the migration login, not by the
    # application. A compromised runtime role must not be able to rewrite or
    # erase migration history, so remove the broad grant from that one table.
    op.execute(f"REVOKE ALL PRIVILEGES ON TABLE alembic_version FROM {APP_ROLE}")
    op.execute(f"GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {APP_ROLE}")
    # Deliberately no ALTER DEFAULT PRIVILEGES. A future table without an
    # explicit grant + RLS policy must fail closed, not become readable by
    # every account just because a migration forgot the policy.

    for table in _PRIVATE_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(f"DROP POLICY IF EXISTS {table}_owner ON {table}")
        op.execute(
            f"CREATE POLICY {table}_owner ON {table} FOR ALL TO {APP_ROLE} "
            f"USING (user_id = nullif(current_setting('app.user_id', true), '')::bigint) "
            f"WITH CHECK (user_id = nullif(current_setting('app.user_id', true), '')::bigint)"
        )

    for table in _GLOBAL_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(f"DROP POLICY IF EXISTS {table}_read ON {table}")
        op.execute(
            f"CREATE POLICY {table}_read ON {table} FOR SELECT TO {APP_ROLE} USING (true)"
        )
        op.execute(f"DROP POLICY IF EXISTS {table}_root_write ON {table}")
        op.execute(
            f"CREATE POLICY {table}_root_write ON {table} FOR ALL TO {APP_ROLE} "
            f"USING (current_setting('app.user_role', true) = 'root') "
            f"WITH CHECK (current_setting('app.user_role', true) = 'root')"
        )


def upgrade() -> None:
    _add_app_user_columns()
    _add_ownership_columns()
    _add_storage_backend_columns()
    _backfill_existing_rows()
    _enforce_ownership()
    _replace_foreign_keys()
    _replace_indexes()
    _add_storage_constraints()
    _add_app_user_constraints()
    _enable_rls()


def _disable_rls() -> None:
    for table in _PRIVATE_TABLES:
        op.execute(f"DROP POLICY IF EXISTS {table}_owner ON {table}")
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")

    for table in _GLOBAL_TABLES:
        op.execute(f"DROP POLICY IF EXISTS {table}_read ON {table}")
        op.execute(f"DROP POLICY IF EXISTS {table}_root_write ON {table}")
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")

    op.execute(
        f"""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{APP_ROLE}') THEN
                EXECUTE 'REVOKE ALL PRIVILEGES ON TABLE alembic_version FROM {APP_ROLE}';
                EXECUTE 'REVOKE ALL PRIVILEGES ON ALL TABLES IN SCHEMA public FROM {APP_ROLE}';
                EXECUTE 'REVOKE ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public FROM {APP_ROLE}';
                EXECUTE 'REVOKE USAGE ON SCHEMA public FROM {APP_ROLE}';
                EXECUTE 'ALTER DEFAULT PRIVILEGES IN SCHEMA public '
                        'REVOKE SELECT, INSERT, UPDATE, DELETE ON TABLES FROM {APP_ROLE}';
                EXECUTE 'ALTER DEFAULT PRIVILEGES IN SCHEMA public '
                        'REVOKE USAGE, SELECT ON SEQUENCES FROM {APP_ROLE}';
                -- The role is cluster-wide. Another database (for example a
                -- test or scratch database) may still depend on it, so the
                -- downgrade removes this database's grants but leaves the role.
            END IF;
        END
        $$;
        """
    )


def _drop_storage_constraints() -> None:
    op.drop_constraint(
        op.f("ck_file_ingest_job_storage_backend_key_pair"),
        "file_ingest_job",
        type_="check",
    )
    op.drop_constraint(
        op.f("ck_file_ingest_job_storage_backend_valid"),
        "file_ingest_job",
        type_="check",
    )
    op.drop_constraint(
        op.f("ck_file_storage_backend_key_pair"),
        "file",
        type_="check",
    )
    op.drop_constraint(
        op.f("ck_file_storage_backend_valid"),
        "file",
        type_="check",
    )


def _restore_single_column_foreign_keys() -> None:
    for fk in _COMPOSITE_FKS:
        op.drop_constraint(fk.name, fk.table, type_="foreignkey")
        op.create_foreign_key(
            fk.old_name,
            fk.table,
            fk.referred_table,
            [fk.columns[0]],
            [fk.referred_columns[0]],
            ondelete=fk.old_ondelete,
        )


def _drop_ownership() -> None:
    for table in reversed(_UNIQUE_ID_USER_TABLES):
        op.drop_constraint(f"uq_{table}_id_user_id", table, type_="unique")
    for table in reversed(_USER_ID_TABLES):
        op.drop_constraint(_user_id_fk_name(table), table, type_="foreignkey")
        op.drop_column(table, "user_id")


def _restore_indexes() -> None:
    op.drop_index(
        "ix_frequently_used_prompt_user_id_order",
        table_name="frequently_used_prompt",
    )
    op.drop_index(
        "ix_saved_question_user_id_conversation_id",
        table_name="saved_question",
    )
    op.drop_index(
        "ix_agent_approval_user_id_conversation_status",
        table_name="agent_approval",
    )
    op.drop_index(
        "ix_agent_run_user_id_conversation_status",
        table_name="agent_run",
    )
    op.drop_index("ix_agent_run_user_id_conversation_id", table_name="agent_run")
    op.drop_index(
        "ix_agent_entry_user_id_conversation_id",
        table_name="agent_entry",
    )
    op.drop_index(
        "ix_agent_conversation_user_id_status",
        table_name="agent_conversation",
    )
    op.drop_index(
        "ix_agent_conversation_user_id_last_entry_at",
        table_name="agent_conversation",
    )
    op.drop_constraint(
        "uq_agent_conversation_provider_session_id",
        "agent_conversation",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_agent_conversation_provider_session_id",
        "agent_conversation",
        ["provider_session_id"],
    )

    op.drop_index(
        "ix_file_ingest_job_user_id_status_created",
        table_name="file_ingest_job",
    )
    op.drop_index("uq_file_ingest_job_active_path", table_name="file_ingest_job")
    op.create_index(
        "uq_file_ingest_job_active_path",
        "file_ingest_job",
        ["path"],
        unique=True,
        postgresql_where=sa.text(_INGEST_ACTIVE_PATH_WHERE),
    )

    op.drop_index(
        "ix_memory_summary_user_id_period_end",
        table_name="memory_summary",
    )
    op.drop_index("ix_memory_user_id_time_active", table_name="memory")
    op.drop_index("ix_chunk_ngram_user_id_gram", table_name="chunk_ngram")
    op.drop_index("ix_chunk_user_id_current", table_name="chunk")
    op.drop_index("ix_chunk_user_id_source", table_name="chunk")
    op.drop_index("uq_chunk_current_source_ordinal", table_name="chunk")
    op.create_index(
        "uq_chunk_current_source_ordinal",
        "chunk",
        ["source_kind", "source_id", "chunk_index"],
        unique=True,
        postgresql_where=sa.text(_CHUNK_CURRENT_WHERE),
    )

    op.drop_index("ix_folder_user_id_depth", table_name="folder")
    op.drop_index("ix_folder_user_id_parent_id", table_name="folder")
    op.drop_index("uq_folder_path", table_name="folder")
    op.create_index("uq_folder_path", "folder", ["path"], unique=True)

    op.drop_index("ix_file_user_id_updated_at", table_name="file")
    op.drop_index("uq_file_current_path", table_name="file")
    op.create_index(
        "uq_file_current_path",
        "file",
        ["raw_file_path"],
        unique=True,
        postgresql_where=sa.text(_FILE_CURRENT_PATH_WHERE),
    )


def _drop_app_user_constraints() -> None:
    op.drop_index("uq_app_user_single_root", table_name="app_user")
    op.drop_constraint(
        "fk_app_user_created_by_user_id_app_user",
        "app_user",
        type_="foreignkey",
    )
    op.drop_constraint(
        op.f("ck_app_user_active_disabled"),
        "app_user",
        type_="check",
    )
    op.drop_constraint(
        op.f("ck_app_user_role_valid"),
        "app_user",
        type_="check",
    )
    op.drop_column("app_user", "disabled_at")
    op.drop_column("app_user", "created_by_user_id")
    op.drop_column("app_user", "password_changed_at")
    op.drop_column("app_user", "must_change_password")
    op.drop_column("app_user", "is_active")
    op.drop_column("app_user", "role")


def downgrade() -> None:
    _disable_rls()
    _drop_storage_constraints()
    _restore_indexes()
    _restore_single_column_foreign_keys()
    _drop_ownership()
    _drop_app_user_constraints()
    op.drop_column("file_ingest_job", "storage_backend")
    op.drop_column("file", "storage_backend")
