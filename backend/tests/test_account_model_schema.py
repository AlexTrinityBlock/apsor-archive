"""Schema guards for account endpoint assignments and agent output caps.

The disposable test database is already at ``head``; these tests exercise the
constraints, defaults, and backfill semantics directly. Upgrade and downgrade
are validated separately with the Alembic CLI and are not repeated here.
"""

from typing import Any

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.exc import DataError, IntegrityError

from app.module.agent.domain.agent_domain import (
    COMPACTION_MAX_OUTPUT_TOKENS,
    DEFAULT_COMPACTION_PROMPT,
)

# Mirrors the Q1 backfill in ``a4c9e2f7b1d6_account_model_endpoints.py``.
# The revision is validated by the CLI; repeating the statement here proves its
# semantics against the migrated schema without running a migration mid-test.
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


def _insert_account(engine: Engine, **values: Any) -> int:
    """Insert one account as the owning login and return its id."""
    payload: dict[str, Any] = {
        "username": "schema-user",
        "password_hash": "not-a-real-password-hash",
        **values,
    }
    columns = ", ".join(payload)
    placeholders = ", ".join(f":{name}" for name in payload)
    with engine.begin() as connection:
        return int(
            connection.execute(
                text(
                    f"INSERT INTO app_user ({columns}, created_at, updated_at) "
                    f"VALUES ({placeholders}, now(), now()) RETURNING id"
                ),
                payload,
            ).scalar_one()
        )


def _insert_chat_provider(
    engine: Engine,
    *,
    provider: str = "deepseek",
    model: str = "deepseek-flash",
    priority: int = 0,
    is_active: bool = False,
    **values: Any,
) -> int:
    """Insert one chat endpoint row as the owning login and return its id."""
    payload: dict[str, Any] = {
        "provider": provider,
        "label": provider,
        "model": model,
        "priority": priority,
        "is_active": is_active,
        **values,
    }
    columns = ", ".join(payload)
    placeholders = ", ".join(f":{name}" for name in payload)
    with engine.begin() as connection:
        return int(
            connection.execute(
                text(
                    f"INSERT INTO chat_provider_config ({columns}) "
                    f"VALUES ({placeholders}) RETURNING id"
                ),
                payload,
            ).scalar_one()
        )


def test_aux_reasoning_effort_defaults_to_low(owner_engine: Engine) -> None:
    user_id = _insert_account(owner_engine)

    with owner_engine.connect() as connection:
        value = connection.execute(
            text("SELECT aux_reasoning_effort FROM app_user WHERE id = :user_id"),
            {"user_id": user_id},
        ).scalar_one()

    assert value == "low"


def test_chat_model_longer_than_128_characters_is_rejected(owner_engine: Engine) -> None:
    user_id = _insert_account(owner_engine)

    # ``VARCHAR(128)`` rejects the 129th character before the CHECK sees it, so
    # either database error satisfies the bound. The CHECK itself is proven by
    # the empty-string case below.
    with pytest.raises((DataError, IntegrityError)):
        with owner_engine.begin() as connection:
            connection.execute(
                text("UPDATE app_user SET chat_model = :model WHERE id = :user_id"),
                {"model": "m" * 129, "user_id": user_id},
            )


def test_chat_model_check_rejects_an_empty_model_name(owner_engine: Engine) -> None:
    user_id = _insert_account(owner_engine)

    with pytest.raises(IntegrityError) as error:
        with owner_engine.begin() as connection:
            connection.execute(
                text("UPDATE app_user SET chat_model = '' WHERE id = :user_id"),
                {"user_id": user_id},
            )

    assert "ck_app_user_chat_model_length" in str(error.value)


def test_compaction_threshold_must_be_below_context_window(owner_engine: Engine) -> None:
    user_id = _insert_account(
        owner_engine,
        chat_context_window_tokens=8000,
        chat_compaction_threshold_tokens=7000,
    )

    with pytest.raises(IntegrityError) as error:
        with owner_engine.begin() as connection:
            connection.execute(
                text(
                    "UPDATE app_user SET chat_compaction_threshold_tokens = :threshold "
                    "WHERE id = :user_id"
                ),
                {"threshold": 8000, "user_id": user_id},
            )

    assert "ck_app_user_chat_context_order" in str(error.value)


def test_deleting_a_chat_provider_nulls_both_assignment_columns(
    owner_engine: Engine,
) -> None:
    primary_id = _insert_chat_provider(owner_engine, model="primary-model")
    aux_id = _insert_chat_provider(owner_engine, model="aux-model", priority=1)
    user_id = _insert_account(
        owner_engine,
        chat_provider_config_id=primary_id,
        chat_model="primary-model",
        aux_provider_config_id=aux_id,
        aux_model="aux-model",
    )

    with owner_engine.begin() as connection:
        connection.execute(
            text("DELETE FROM chat_provider_config WHERE id = :provider_id"),
            {"provider_id": primary_id},
        )
        connection.execute(
            text("DELETE FROM chat_provider_config WHERE id = :provider_id"),
            {"provider_id": aux_id},
        )
        row = connection.execute(
            text(
                "SELECT chat_provider_config_id, aux_provider_config_id "
                "FROM app_user WHERE id = :user_id"
            ),
            {"user_id": user_id},
        ).one()

    assert tuple(row) == (None, None)


def test_q1_backfill_assigns_the_lowest_priority_active_chat_row(
    owner_engine: Engine,
) -> None:
    user_id = _insert_account(owner_engine)
    already_assigned = _insert_chat_provider(owner_engine, model="existing-model")
    assigned_user_id = _insert_account(
        owner_engine,
        username="already-assigned-user",
        chat_provider_config_id=already_assigned,
        chat_model="existing-model",
    )
    _insert_chat_provider(
        owner_engine,
        model="inactive-model",
        priority=0,
        is_active=False,
    )
    _insert_chat_provider(
        owner_engine,
        provider="none",
        model="disabled-model",
        priority=1,
        is_active=True,
    )
    selected_id = _insert_chat_provider(
        owner_engine,
        provider="openai-compatible",
        model="selected-model",
        priority=2,
        is_active=True,
    )
    _insert_chat_provider(
        owner_engine,
        model="backup-model",
        priority=5,
        is_active=True,
    )

    with owner_engine.begin() as connection:
        connection.execute(text(_Q1_BACKFILL))
        assigned = connection.execute(
            text(
                "SELECT chat_provider_config_id, chat_model "
                "FROM app_user WHERE id = :user_id"
            ),
            {"user_id": user_id},
        ).one()
        preserved = connection.execute(
            text(
                "SELECT chat_provider_config_id, chat_model "
                "FROM app_user WHERE id = :user_id"
            ),
            {"user_id": assigned_user_id},
        ).one()

    assert tuple(assigned) == (selected_id, "selected-model")
    assert tuple(preserved) == (already_assigned, "existing-model")


def test_q1_backfill_leaves_accounts_unassigned_without_an_active_chat_row(
    owner_engine: Engine,
) -> None:
    user_id = _insert_account(owner_engine)
    _insert_chat_provider(
        owner_engine,
        model="inactive-model",
        priority=0,
        is_active=False,
    )
    _insert_chat_provider(
        owner_engine,
        provider="none",
        model="disabled-model",
        priority=1,
        is_active=True,
    )

    with owner_engine.begin() as connection:
        connection.execute(text(_Q1_BACKFILL))
        row = connection.execute(
            text(
                "SELECT chat_provider_config_id, chat_model "
                "FROM app_user WHERE id = :user_id"
            ),
            {"user_id": user_id},
        ).one()

    assert tuple(row) == (None, None)


def test_chat_provider_accepts_anthropic_and_rejects_unknown_providers(
    owner_engine: Engine,
) -> None:
    anthropic_id = _insert_chat_provider(
        owner_engine,
        provider="anthropic",
        model="claude-haiku-5-5",
        max_output_tokens=8192,
    )
    assert anthropic_id > 0

    with pytest.raises(IntegrityError) as error:
        _insert_chat_provider(
            owner_engine,
            provider="gemini",
            model="gemini-pro",
        )

    assert "ck_chat_provider_config_provider_valid" in str(error.value)


def test_agent_config_has_the_new_columns_with_defaults(owner_engine: Engine) -> None:
    with owner_engine.begin() as connection:
        connection.execute(text("INSERT INTO agent_config (id) VALUES (1)"))
        row = (
            connection.execute(
                text(
                    "SELECT model_escalation_enabled, compaction_prompt, "
                    "compaction_max_output_tokens, agent_max_output_tokens "
                    "FROM agent_config WHERE id = 1"
                )
            )
            .mappings()
            .one()
        )

    assert row["model_escalation_enabled"] is True
    assert row["compaction_prompt"] == DEFAULT_COMPACTION_PROMPT
    assert "{max_output_tokens}" in row["compaction_prompt"]
    assert row["compaction_max_output_tokens"] == COMPACTION_MAX_OUTPUT_TOKENS
    assert COMPACTION_MAX_OUTPUT_TOKENS == 2600
    assert row["agent_max_output_tokens"] == 64000
