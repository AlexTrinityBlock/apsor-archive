"""allow Exa in the two web provider tables

Revision ID: a3e7c1d9b2f4
Revises: f7a3c2d9e1b4
Create Date: 2026-11-07 16:55:00.000000

The provider registry already exposes ``exa`` as an allowed web provider, but
the original check constraints only admitted ``tavily`` and ``none``. Extend
both web capability tables so an Exa provider row can be stored and selected
from the Settings UI.

Downgrade restores the narrower constraint. It deliberately fails if an Exa row
still exists rather than silently deleting a configured provider.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "a3e7c1d9b2f4"
down_revision: str | None = "f7a3c2d9e1b4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_WEB_TABLES = ("web_search_provider_config", "web_fetch_provider_config")


def _replace_provider_check(*, allow_exa: bool) -> None:
    providers = "'tavily', 'exa', 'none'" if allow_exa else "'tavily', 'none'"
    for table_name in _WEB_TABLES:
        # ``op.f`` marks the name as final; without it the metadata naming
        # convention prefixes the constraint a second time
        # (``ck_<table>_ck_<table>_provider_valid``).
        constraint_name = op.f(f"ck_{table_name}_provider_valid")
        op.drop_constraint(constraint_name, table_name, type_="check")
        op.create_check_constraint(
            constraint_name,
            table_name,
            f"provider IN ({providers})",
        )


def upgrade() -> None:
    _replace_provider_check(allow_exa=True)


def downgrade() -> None:
    _replace_provider_check(allow_exa=False)
