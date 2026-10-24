"""replace the unified tree with explicit folders

Revision ID: c4d8e2f6a1b9
Revises: 8f4b2c6d9e01
Create Date: 2026-10-24 18:40:00.000000

A folder is now the only hierarchy record. File leaves are derived from
``file.raw_file_path``, so ``tree_node`` no longer needs one row per file
version. Existing folders keep their ids, which preserves ``parent_id`` links.

The downgrade recreates current folder rows and current file leaves. Historical
file leaves are not reconstructed; the file table already keeps those versions.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c4d8e2f6a1b9"
down_revision: str | None = "8f4b2c6d9e01"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_COPY_FOLDERS = """
INSERT INTO folder (id, parent_id, path, name, depth, created_at, updated_at)
SELECT id, parent_id, path, name, depth, created_at, updated_at
FROM tree_node
WHERE kind = 'folder' AND is_current AND deleted_at IS NULL
ORDER BY depth, id
"""

_COPY_FOLDER_NODES = """
INSERT INTO tree_node
    (id, parent_id, path, name, kind, file_id, depth, is_current,
     superseded_by_id, created_at, updated_at, deleted_at)
SELECT id, parent_id, path, name, 'folder', NULL, depth, true,
       NULL, created_at, updated_at, NULL
FROM folder
ORDER BY depth, id
"""

_COPY_FILE_NODES = """
INSERT INTO tree_node
    (parent_id, path, name, kind, file_id, depth, is_current, created_at, updated_at)
SELECT f.id,
       fi.raw_file_path,
       fi.file_name,
       'file',
       fi.id,
       array_length(string_to_array(btrim(fi.raw_file_path, '/'), '/'), 1),
       true,
       fi.created_at,
       fi.updated_at
FROM file fi
LEFT JOIN folder f
    ON f.path = NULLIF(
        rtrim(regexp_replace(fi.raw_file_path, '/[^/]+$', ''), '/'),
        ''
    )
WHERE fi.is_current AND fi.deleted_at IS NULL
ORDER BY fi.id
"""


def _create_folder_table() -> None:
    op.create_table(
        "folder",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("parent_id", sa.BigInteger(), nullable=True),
        sa.Column("path", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("depth", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("depth >= 1", name=op.f("ck_folder_depth_positive")),
        sa.ForeignKeyConstraint(
            ["parent_id"],
            ["folder.id"],
            name=op.f("fk_folder_parent_id_folder"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_folder")),
    )
    op.create_index("uq_folder_path", "folder", ["path"], unique=True)
    op.create_index("ix_folder_parent_id", "folder", ["parent_id"], unique=False)
    op.create_index("ix_folder_depth", "folder", ["depth"], unique=False)


def _create_tree_node_table() -> None:
    op.create_table(
        "tree_node",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("parent_id", sa.BigInteger(), nullable=True),
        sa.Column("path", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("file_id", sa.BigInteger(), nullable=True),
        sa.Column("depth", sa.Integer(), nullable=False),
        sa.Column("is_current", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("superseded_by_id", sa.BigInteger(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "(kind = 'file' AND file_id IS NOT NULL) OR (kind = 'folder' AND file_id IS NULL)",
            name=op.f("ck_tree_node_file_id_matches_kind"),
        ),
        sa.CheckConstraint("kind IN ('folder', 'file')", name=op.f("ck_tree_node_kind_valid")),
        sa.CheckConstraint("depth >= 1", name=op.f("ck_tree_node_depth_positive")),
        sa.ForeignKeyConstraint(
            ["file_id"], ["file.id"], name=op.f("fk_tree_node_file_id_file"), ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["parent_id"],
            ["tree_node.id"],
            name=op.f("fk_tree_node_parent_id_tree_node"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["superseded_by_id"],
            ["tree_node.id"],
            name=op.f("fk_tree_node_superseded_by_id_tree_node"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tree_node")),
    )
    op.create_index("ix_tree_node_file_id", "tree_node", ["file_id"], unique=False)
    op.create_index("ix_tree_node_parent_id", "tree_node", ["parent_id"], unique=False)
    op.create_index("ix_tree_node_path", "tree_node", ["path"], unique=False)
    op.create_index(
        "uq_tree_node_current_path",
        "tree_node",
        ["path"],
        unique=True,
        postgresql_where=sa.text("is_current AND deleted_at IS NULL"),
    )


def upgrade() -> None:
    _create_folder_table()

    op.execute(_COPY_FOLDERS)
    op.execute(
        "SELECT setval("
        "pg_get_serial_sequence('folder', 'id'), "
        "COALESCE((SELECT MAX(id) FROM folder), 0) + 1, "
        "false)"
    )

    op.drop_index(
        "uq_tree_node_current_path",
        table_name="tree_node",
        postgresql_where=sa.text("is_current AND deleted_at IS NULL"),
    )
    op.drop_index("ix_tree_node_parent_id", table_name="tree_node")
    op.drop_index("ix_tree_node_path", table_name="tree_node")
    op.drop_index("ix_tree_node_file_id", table_name="tree_node")
    op.drop_table("tree_node")


def downgrade() -> None:
    _create_tree_node_table()

    op.execute(_COPY_FOLDER_NODES)
    op.execute(
        "SELECT setval("
        "pg_get_serial_sequence('tree_node', 'id'), "
        "COALESCE((SELECT MAX(id) FROM tree_node), 0) + 1, "
        "false)"
    )
    op.execute(_COPY_FILE_NODES)

    op.drop_index("ix_folder_depth", table_name="folder")
    op.drop_index("ix_folder_parent_id", table_name="folder")
    op.drop_index("uq_folder_path", table_name="folder")
    op.drop_table("folder")
