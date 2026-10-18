"""agent page context entry kind

Revision ID: c4f1a9e2b7d3
Revises: a7c41e9d2b60
Create Date: 2026-10-19 12:00:00.000000

"""

from collections.abc import Sequence

from alembic import op

revision: str = "c4f1a9e2b7d3"
down_revision: str | None = "a7c41e9d2b60"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_KIND_VALID = (
    "kind IN ('pi.user', 'pi.assistant', 'pi.tool-result', "
    "'pi.page-context', 'pi.system', 'pi.reset', 'pi.compaction', "
    "'ui.notice')"
)
_MODEL_REQUIRED = (
    "kind NOT IN ('pi.user', 'pi.assistant', 'pi.tool-result', "
    "'pi.page-context', 'pi.system') OR model IS NOT NULL"
)
_OLD_KIND_VALID = (
    "kind IN ('pi.user', 'pi.assistant', 'pi.tool-result', 'pi.system', "
    "'pi.reset', 'pi.compaction', 'ui.notice')"
)
_OLD_MODEL_REQUIRED = (
    "kind NOT IN ('pi.user', 'pi.assistant', 'pi.tool-result', 'pi.system') "
    "OR model IS NOT NULL"
)


def upgrade() -> None:
    op.drop_constraint(
        op.f("ck_agent_entry_kind_valid"),
        "agent_entry",
        type_="check",
    )
    op.create_check_constraint(
        op.f("ck_agent_entry_kind_valid"),
        "agent_entry",
        _KIND_VALID,
    )
    op.drop_constraint(
        op.f("ck_agent_entry_model_required"),
        "agent_entry",
        type_="check",
    )
    op.create_check_constraint(
        op.f("ck_agent_entry_model_required"),
        "agent_entry",
        _MODEL_REQUIRED,
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("ck_agent_entry_model_required"),
        "agent_entry",
        type_="check",
    )
    op.create_check_constraint(
        op.f("ck_agent_entry_model_required"),
        "agent_entry",
        _OLD_MODEL_REQUIRED,
    )
    op.drop_constraint(
        op.f("ck_agent_entry_kind_valid"),
        "agent_entry",
        type_="check",
    )
    op.create_check_constraint(
        op.f("ck_agent_entry_kind_valid"),
        "agent_entry",
        _OLD_KIND_VALID,
    )
