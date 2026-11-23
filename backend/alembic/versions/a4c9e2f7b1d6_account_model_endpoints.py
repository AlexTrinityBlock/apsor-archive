"""account model assignments and dual chat endpoints

Revision ID: a4c9e2f7b1d6
Revises: b3d7e9f1c2a4
Create Date: 2026-11-23 12:00:00.000000

Adds the per-account endpoint assignment and the two bounded budgets it needs:

* eight ``app_user`` columns (primary and auxiliary endpoint, free-text model
  and effort for each, context window and compaction threshold), two
  ``ON DELETE SET NULL`` foreign keys into ``chat_provider_config``, and seven
  CHECK constraints. ``app_user`` deliberately stays outside row-level
  security, so no policy or grant change is required.
* ``chat_provider_config.max_output_tokens`` with its range CHECK, plus the
  widened provider CHECK that admits ``anthropic``.
* four ``agent_config`` columns for the escalation switch, the deterministic
  compaction template, its output cap, and the agent output cap. The template
  default and its token cap live in ``agent_domain`` so the model, this
  migration, and the settings surface cannot drift.

After the columns and the foreign keys exist, the Q1 backfill copies the
lowest ``(priority, id)`` active non-``none`` chat row id and its model to every
account that has no assignment yet. It copies the row even when the key is
missing: resolution rejects that endpoint later, and the migration does not
guess a replacement. With no such row the UPDATE is a no-op and every account
stays unassigned; there is no environment fallback to inherit.

Downgrade drops the columns and therefore discards every assignment. It
refuses to restore the narrower provider CHECK while a row with
``provider='anthropic'`` exists, rather than silently breaking a configured
provider; delete or reassign that row first.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from app.module.agent.domain.agent_domain import (
    COMPACTION_MAX_OUTPUT_TOKENS,
    DEFAULT_COMPACTION_PROMPT,
)

revision: str = "a4c9e2f7b1d6"
down_revision: str | None = "b3d7e9f1c2a4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# ``aux_reasoning_effort`` is added separately because it is NOT NULL with a
# server default; every other assignment column stays nullable.
_APP_USER_COLUMNS = (
    ("chat_provider_config_id", sa.BigInteger()),
    ("chat_model", sa.String(length=128)),
    ("chat_reasoning_effort", sa.String(length=32)),
    ("aux_provider_config_id", sa.BigInteger()),
    ("aux_model", sa.String(length=128)),
    ("chat_context_window_tokens", sa.Integer()),
    ("chat_compaction_threshold_tokens", sa.Integer()),
)

_APP_USER_CHECKS = (
    (
        "chat_model_length",
        "chat_model IS NULL OR char_length(chat_model) BETWEEN 1 AND 128",
    ),
    (
        "aux_model_length",
        "aux_model IS NULL OR char_length(aux_model) BETWEEN 1 AND 128",
    ),
    (
        "chat_effort_length",
        "chat_reasoning_effort IS NULL "
        "OR char_length(chat_reasoning_effort) BETWEEN 1 AND 32",
    ),
    ("aux_effort_length", "char_length(aux_reasoning_effort) BETWEEN 1 AND 32"),
    (
        "chat_context_window",
        "chat_context_window_tokens IS NULL "
        "OR chat_context_window_tokens BETWEEN 8000 AND 2000000",
    ),
    (
        "chat_compaction_threshold",
        "chat_compaction_threshold_tokens IS NULL "
        "OR chat_compaction_threshold_tokens BETWEEN 1000 AND 1000000",
    ),
    (
        "chat_context_order",
        "chat_compaction_threshold_tokens IS NULL "
        "OR chat_context_window_tokens IS NULL "
        "OR chat_compaction_threshold_tokens < chat_context_window_tokens",
    ),
)

_APP_USER_FOREIGN_KEYS = (
    "fk_app_user_chat_provider_config_id_chat_provider_config",
    "fk_app_user_aux_provider_config_id_chat_provider_config",
)

_CHAT_PROVIDERS_WITH_ANTHROPIC = (
    "provider IN ('anthropic', 'deepseek', 'openai-compatible', 'none')"
)
_CHAT_PROVIDERS_WITHOUT_ANTHROPIC = (
    "provider IN ('deepseek', 'openai-compatible', 'none')"
)

# Q1: an account that already has an assignment keeps it. A deployment with no
# active chat row leaves every account unassigned on purpose.
_Q1_BACKFILL = """
UPDATE app_user
SET chat_provider_config_id = primary_row.id,
    chat_model = primary_row.model
FROM (
    SELECT id, model
    FROM chat_provider_config
    WHERE is_active AND provider <> 'none'
    ORDER BY priority, id
    LIMIT 1
) AS primary_row
WHERE app_user.chat_provider_config_id IS NULL
"""


def _require_no_anthropic_rows() -> None:
    """Refuse to restore a provider CHECK that would reject existing rows."""
    exists = (
        op.get_bind()
        .execute(
            sa.text(
                "SELECT 1 FROM chat_provider_config "
                "WHERE provider = 'anthropic' LIMIT 1"
            )
        )
        .first()
    )
    if exists is not None:
        raise RuntimeError(
            "cannot downgrade a4c9e2f7b1d6 while a chat_provider_config row has "
            "provider='anthropic'; reassign or delete those rows first"
        )


def upgrade() -> None:
    for name, column_type in _APP_USER_COLUMNS:
        op.add_column("app_user", sa.Column(name, column_type, nullable=True))
    op.add_column(
        "app_user",
        sa.Column(
            "aux_reasoning_effort",
            sa.String(length=32),
            server_default=sa.text("'low'"),
            nullable=False,
        ),
    )
    op.create_foreign_key(
        op.f("fk_app_user_chat_provider_config_id_chat_provider_config"),
        "app_user",
        "chat_provider_config",
        ["chat_provider_config_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        op.f("fk_app_user_aux_provider_config_id_chat_provider_config"),
        "app_user",
        "chat_provider_config",
        ["aux_provider_config_id"],
        ["id"],
        ondelete="SET NULL",
    )
    for suffix, clause in _APP_USER_CHECKS:
        op.create_check_constraint(op.f(f"ck_app_user_{suffix}"), "app_user", clause)

    op.execute(sa.text(_Q1_BACKFILL))

    op.add_column(
        "chat_provider_config",
        sa.Column("max_output_tokens", sa.Integer(), nullable=True),
    )
    op.create_check_constraint(
        op.f("ck_chat_provider_config_max_output_tokens_range"),
        "chat_provider_config",
        "max_output_tokens IS NULL OR max_output_tokens BETWEEN 256 AND 131072",
    )
    # ``op.f`` marks the name as final; without it the metadata naming
    # convention prefixes the constraint a second time.
    op.drop_constraint(
        op.f("ck_chat_provider_config_provider_valid"),
        "chat_provider_config",
        type_="check",
    )
    op.create_check_constraint(
        op.f("ck_chat_provider_config_provider_valid"),
        "chat_provider_config",
        _CHAT_PROVIDERS_WITH_ANTHROPIC,
    )

    op.add_column(
        "agent_config",
        sa.Column(
            "model_escalation_enabled",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
    )
    op.add_column(
        "agent_config",
        sa.Column(
            "compaction_prompt",
            sa.Text(),
            server_default=DEFAULT_COMPACTION_PROMPT,
            nullable=False,
        ),
    )
    op.add_column(
        "agent_config",
        sa.Column(
            "compaction_max_output_tokens",
            sa.Integer(),
            server_default=sa.text(str(COMPACTION_MAX_OUTPUT_TOKENS)),
            nullable=False,
        ),
    )
    op.add_column(
        "agent_config",
        sa.Column(
            "agent_max_output_tokens",
            sa.Integer(),
            server_default=sa.text("64000"),
            nullable=False,
        ),
    )
    op.create_check_constraint(
        op.f("ck_agent_config_compaction_max_output_tokens"),
        "agent_config",
        "compaction_max_output_tokens BETWEEN 256 AND 16384",
    )
    op.create_check_constraint(
        op.f("ck_agent_config_agent_max_output_tokens"),
        "agent_config",
        "agent_max_output_tokens BETWEEN 256 AND 131072",
    )
    op.create_check_constraint(
        op.f("ck_agent_config_compaction_prompt_length"),
        "agent_config",
        "char_length(compaction_prompt) BETWEEN 1 AND 20000",
    )
    op.create_check_constraint(
        op.f("ck_agent_config_compaction_prompt_placeholder"),
        "agent_config",
        "position('{max_output_tokens}' IN compaction_prompt) > 0",
    )


def downgrade() -> None:
    for suffix in (
        "compaction_prompt_placeholder",
        "compaction_prompt_length",
        "agent_max_output_tokens",
        "compaction_max_output_tokens",
    ):
        op.drop_constraint(op.f(f"ck_agent_config_{suffix}"), "agent_config", type_="check")
    for column in (
        "agent_max_output_tokens",
        "compaction_max_output_tokens",
        "compaction_prompt",
        "model_escalation_enabled",
    ):
        op.drop_column("agent_config", column)

    _require_no_anthropic_rows()
    op.drop_constraint(
        op.f("ck_chat_provider_config_max_output_tokens_range"),
        "chat_provider_config",
        type_="check",
    )
    op.drop_column("chat_provider_config", "max_output_tokens")
    op.drop_constraint(
        op.f("ck_chat_provider_config_provider_valid"),
        "chat_provider_config",
        type_="check",
    )
    op.create_check_constraint(
        op.f("ck_chat_provider_config_provider_valid"),
        "chat_provider_config",
        _CHAT_PROVIDERS_WITHOUT_ANTHROPIC,
    )

    for suffix, _ in reversed(_APP_USER_CHECKS):
        op.drop_constraint(op.f(f"ck_app_user_{suffix}"), "app_user", type_="check")
    for constraint_name in reversed(_APP_USER_FOREIGN_KEYS):
        op.drop_constraint(op.f(constraint_name), "app_user", type_="foreignkey")
    op.drop_column("app_user", "aux_reasoning_effort")
    for name, _ in reversed(_APP_USER_COLUMNS):
        op.drop_column("app_user", name)
