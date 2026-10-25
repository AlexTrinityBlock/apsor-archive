"""raise the per-turn tool call default

Revision ID: b8f4c2d9e6a1
Revises: e5c1a9d3b7f2
Create Date: 2026-10-25 23:30:00.000000

Migration decisions:
- The default per-turn tool call budget was 6, which failed a real turn that
  needed a seventh read before it could answer. The new default is 20.
- Upgrade changes the server default and promotes the stored singleton row only
  when it still holds the old default. A value the owner chose deliberately is
  never overwritten.
- Downgrade restores the old server default but leaves the stored value alone:
  the previous schema already accepted 1-24, so a stored 20 stays valid.
- The numbers are embedded here on purpose so the migration remains
  reproducible even if the runtime constants change again.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "b8f4c2d9e6a1"
down_revision: str | None = "e5c1a9d3b7f2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OLD_DEFAULT = 6
NEW_DEFAULT = 20


def upgrade() -> None:
    op.alter_column(
        "agent_config",
        "max_tool_calls_per_turn",
        existing_type=sa.Integer(),
        existing_nullable=False,
        server_default=sa.text(str(NEW_DEFAULT)),
    )
    op.execute(
        sa.text(
            "UPDATE agent_config "
            "SET max_tool_calls_per_turn = :new_default, updated_at = now() "
            "WHERE max_tool_calls_per_turn = :old_default"
        ).bindparams(new_default=NEW_DEFAULT, old_default=OLD_DEFAULT)
    )


def downgrade() -> None:
    op.alter_column(
        "agent_config",
        "max_tool_calls_per_turn",
        existing_type=sa.Integer(),
        existing_nullable=False,
        server_default=sa.text(str(OLD_DEFAULT)),
    )
