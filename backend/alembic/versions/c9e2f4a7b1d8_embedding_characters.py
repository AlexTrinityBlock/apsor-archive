"""measure embedding usage in characters

Revision ID: c9e2f4a7b1d8
Revises: b7c4e2f9a1d3
Create Date: 2026-11-18 18:00:00.000000

Renames ``app_user.embedding_tokens`` to ``app_user.embedding_characters``.
The historical column already stored zero for every account, so a rename keeps
the data and the existing grant semantics intact. Embedding allowances are now
measured in input characters rather than estimated provider tokens.

The old ``usage_non_negative`` check references the old column name, so it is
dropped and recreated around the rename in both directions. The old revision is
left untouched as history.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c9e2f4a7b1d8"
down_revision: str | None = "b7c4e2f9a1d3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_USAGE_NON_NEGATIVE_WITH_CHARACTERS = (
    "prompt_tokens >= 0 AND completion_tokens >= 0 AND total_tokens >= 0 "
    "AND cached_tokens >= 0 AND api_calls >= 0 AND agent_turns >= 0 "
    "AND embedding_characters >= 0 AND web_search_calls >= 0 "
    "AND web_fetch_calls >= 0"
)
_USAGE_NON_NEGATIVE_WITH_TOKENS = (
    "prompt_tokens >= 0 AND completion_tokens >= 0 AND total_tokens >= 0 "
    "AND cached_tokens >= 0 AND api_calls >= 0 AND agent_turns >= 0 "
    "AND embedding_tokens >= 0 AND web_search_calls >= 0 "
    "AND web_fetch_calls >= 0"
)


def upgrade() -> None:
    op.drop_constraint(
        op.f("ck_app_user_usage_non_negative"),
        "app_user",
        type_="check",
    )
    op.alter_column(
        "app_user",
        "embedding_tokens",
        new_column_name="embedding_characters",
        existing_type=sa.BigInteger(),
        existing_nullable=False,
        existing_server_default=sa.text("0"),
    )
    op.create_check_constraint(
        op.f("ck_app_user_usage_non_negative"),
        "app_user",
        _USAGE_NON_NEGATIVE_WITH_CHARACTERS,
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("ck_app_user_usage_non_negative"),
        "app_user",
        type_="check",
    )
    op.alter_column(
        "app_user",
        "embedding_characters",
        new_column_name="embedding_tokens",
        existing_type=sa.BigInteger(),
        existing_nullable=False,
        existing_server_default=sa.text("0"),
    )
    op.create_check_constraint(
        op.f("ck_app_user_usage_non_negative"),
        "app_user",
        _USAGE_NON_NEGATIVE_WITH_TOKENS,
    )
