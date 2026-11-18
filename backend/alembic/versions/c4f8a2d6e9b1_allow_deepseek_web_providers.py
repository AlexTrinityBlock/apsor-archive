"""allow DeepSeek in the two web provider tables

Revision ID: c4f8a2d6e9b1
Revises: a9c3e7f1d5b2
Create Date: 2026-11-18 10:00:00.000000

The provider registry exposes ``deepseek`` as an allowed web search and fetch
provider, but the current check constraints only admit ``tavily``, ``exa``, and
``none``. Extend both web capability tables so a DeepSeek provider row can be
stored and selected from the Settings UI.

Downgrade restores the narrower constraint. It deliberately fails if a DeepSeek
row still exists rather than silently deleting a configured provider.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "c4f8a2d6e9b1"
down_revision: str | None = "a9c3e7f1d5b2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_WEB_TABLES = ("web_search_provider_config", "web_fetch_provider_config")


def _replace_provider_check(*, allow_deepseek: bool) -> None:
    providers = (
        "'tavily', 'exa', 'deepseek', 'none'"
        if allow_deepseek
        else "'tavily', 'exa', 'none'"
    )
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
    _replace_provider_check(allow_deepseek=True)


def downgrade() -> None:
    _replace_provider_check(allow_deepseek=False)
