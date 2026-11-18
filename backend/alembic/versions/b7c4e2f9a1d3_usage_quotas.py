"""per-account usage allowances for chat, embedding, web search, and fetch

Revision ID: b7c4e2f9a1d3
Revises: d9b3e7f1c5a2
Create Date: 2026-11-18 15:00:00.000000

Adds four independent allowance categories to ``app_user``. Chat reuses the
existing ``total_tokens`` lifetime counter maintained by the agent-run trigger,
so no second chat counter and no trigger change are needed. Embedding tokens,
web search calls, and web fetch calls get new lifetime counters.

Every new row and every existing account defaults to enabled with a NULL grant,
which means unlimited and preserves today's behavior. ``*_used_before_reset``
records the lifetime value at the last admin reset; the current cycle is
``max(0, lifetime - used_before_reset)``.

``app_user`` is deliberately outside row-level security, so no policy or grant
change is required. The new columns are reached only through the auth/account
paths and the captured-user quota service.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "b7c4e2f9a1d3"
down_revision: str | None = "d9b3e7f1c5a2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_USAGE_NON_NEGATIVE = (
    "prompt_tokens >= 0 AND completion_tokens >= 0 AND total_tokens >= 0 "
    "AND cached_tokens >= 0 AND api_calls >= 0 AND agent_turns >= 0"
)
_USAGE_NON_NEGATIVE_WITH_QUOTAS = (
    _USAGE_NON_NEGATIVE
    + " AND embedding_tokens >= 0 AND web_search_calls >= 0 "
    "AND web_fetch_calls >= 0"
)
_QUOTA_NON_NEGATIVE = (
    "(chat_granted IS NULL OR chat_granted >= 0) "
    "AND (embedding_granted IS NULL OR embedding_granted >= 0) "
    "AND (web_search_granted IS NULL OR web_search_granted >= 0) "
    "AND (web_fetch_granted IS NULL OR web_fetch_granted >= 0) "
    "AND chat_used_before_reset >= 0 "
    "AND embedding_used_before_reset >= 0 "
    "AND web_search_used_before_reset >= 0 "
    "AND web_fetch_used_before_reset >= 0"
)

_COUNTER_COLUMNS = (
    "embedding_tokens",
    "web_search_calls",
    "web_fetch_calls",
)
_ENABLED_COLUMNS = (
    "chat_enabled",
    "embedding_enabled",
    "web_search_enabled",
    "web_fetch_enabled",
)
_GRANTED_COLUMNS = (
    "chat_granted",
    "embedding_granted",
    "web_search_granted",
    "web_fetch_granted",
)
_BASE_COLUMNS = (
    "chat_used_before_reset",
    "embedding_used_before_reset",
    "web_search_used_before_reset",
    "web_fetch_used_before_reset",
)


def upgrade() -> None:
    for column in _ENABLED_COLUMNS:
        op.add_column(
            "app_user",
            sa.Column(
                column,
                sa.Boolean(),
                server_default=sa.text("true"),
                nullable=False,
            ),
        )
    for column in (*_GRANTED_COLUMNS, *_BASE_COLUMNS, *_COUNTER_COLUMNS):
        op.add_column(
            "app_user",
            sa.Column(
                column,
                sa.BigInteger(),
                server_default=(
                    sa.text("0")
                    if column in _COUNTER_COLUMNS + _BASE_COLUMNS
                    else None
                ),
                nullable=column in _GRANTED_COLUMNS,
            ),
        )

    op.drop_constraint(
        op.f("ck_app_user_usage_non_negative"),
        "app_user",
        type_="check",
    )
    op.create_check_constraint(
        op.f("ck_app_user_usage_non_negative"),
        "app_user",
        _USAGE_NON_NEGATIVE_WITH_QUOTAS,
    )
    op.create_check_constraint(
        op.f("ck_app_user_quota_non_negative"),
        "app_user",
        _QUOTA_NON_NEGATIVE,
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("ck_app_user_quota_non_negative"),
        "app_user",
        type_="check",
    )
    op.drop_constraint(
        op.f("ck_app_user_usage_non_negative"),
        "app_user",
        type_="check",
    )
    for column in reversed(
        (*_ENABLED_COLUMNS, *_GRANTED_COLUMNS, *_BASE_COLUMNS, *_COUNTER_COLUMNS)
    ):
        op.drop_column("app_user", column)
    op.create_check_constraint(
        op.f("ck_app_user_usage_non_negative"),
        "app_user",
        _USAGE_NON_NEGATIVE,
    )
