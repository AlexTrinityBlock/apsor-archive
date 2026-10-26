"""agent usage accounting and root impersonation sessions

Revision ID: f9c2a7d4e6b1
Revises: e8f1c4d2a7b9
Create Date: 2026-10-26 00:00:00.000000

Migration decisions:
- ``agent_run`` stores one turn's provider counters. ``api_calls`` counts
  successful or malformed provider completions that returned a usage object;
  synthetic failure entries with no usage are excluded. A tool loop with three
  provider round trips records three calls.
- ``app_user`` stores the per-account rollup. A trigger on ``agent_run`` keeps
  it current for INSERT/UPDATE/DELETE. The trigger is created after the
  historical backfill so existing rows are not counted twice. Delete and
  actor-change paths recompute ``last_agent_activity_at`` from the remaining
  runs instead of leaving a stale maximum.
- Historical counters are derived from ``agent_entry.data->'usage'`` for
  assistant entries with ``by_run_id`` and a JSON-object ``usage`` value. JSON
  values are only cast when they are numbers with a bounded integer shape, so a
  malformed historical row cannot fail the migration. ``total_tokens`` falls
  back to prompt + completion when the provider omitted the key or reported
  zero; ``cached_tokens`` uses ``prompt_cache_hit_tokens``.
- The upgrade preflight requires a migration role that is a superuser or has
  ``BYPASSRLS``. Otherwise FORCE RLS would silently hide rows from the
  historical read and produce an incomplete backfill.
- ``user_session.impersonator_user_id`` marks a target session created by root.
  Deleting the actor removes the impersonation sessions it started.
- Downgrade drops the trigger/function first, then the added constraints,
  index, foreign key, and columns.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "f9c2a7d4e6b1"
down_revision: str | None = "e8f1c4d2a7b9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_USAGE_COLUMNS: tuple[str, ...] = (
    "prompt_tokens",
    "completion_tokens",
    "total_tokens",
    "cached_tokens",
    "api_calls",
)

_USAGE_NUMBER_REGEX = r"^-?[0-9]{1,15}(\.[0-9]+)?$"


def _usage_counter_sql(key: str) -> str:
    """Read one bounded, non-negative integer from an entry's usage JSON."""
    json_value = f"entry.data->'usage'->'{key}'"
    raw_value = f"entry.data->'usage'->>'{key}'"
    return (
        f"CASE WHEN jsonb_typeof({json_value}) = 'number' "
        f"AND ({raw_value}) ~ '{_USAGE_NUMBER_REGEX}' "
        f"THEN GREATEST(0, (({raw_value})::numeric)::bigint) "
        f"ELSE 0 END"
    )


def _usage_total_sql() -> str:
    """Prefer a non-zero provider total, else fall back to prompt + completion."""
    json_value = "entry.data->'usage'->'total_tokens'"
    raw_value = "entry.data->'usage'->>'total_tokens'"
    reported = (
        f"CASE WHEN jsonb_typeof({json_value}) = 'number' "
        f"AND ({raw_value}) ~ '{_USAGE_NUMBER_REGEX}' "
        f"THEN GREATEST(0, (({raw_value})::numeric)::bigint) "
        f"ELSE NULL END"
    )
    fallback = (
        f"({_usage_counter_sql('prompt_tokens')} "
        f"+ {_usage_counter_sql('completion_tokens')})"
    )
    return f"COALESCE(NULLIF({reported}, 0), {fallback})"


def _assert_migration_role_can_bypass_rls() -> None:
    """Fail loudly if FORCE RLS would silently hide the historical rows."""
    privileged = (
        op.get_bind()
        .execute(
            sa.text(
                "SELECT rolsuper OR rolbypassrls FROM pg_roles WHERE rolname = current_user"
            )
        )
        .scalar_one_or_none()
    )
    if not privileged:
        raise RuntimeError(
            "Migration f9c2a7d4e6b1 must run as a superuser or a role with BYPASSRLS "
            "so the historical usage backfill can read forced-RLS tables."
        )


def _backfill_agent_runs() -> None:
    op.execute(
        sa.text(
            f"""
            WITH assistant_usage AS (
                SELECT
                    entry.by_run_id AS run_id,
                    {_usage_counter_sql("prompt_tokens")} AS prompt_tokens,
                    {_usage_counter_sql("completion_tokens")} AS completion_tokens,
                    {_usage_counter_sql("prompt_cache_hit_tokens")} AS cached_tokens,
                    {_usage_total_sql()} AS total_tokens
                FROM agent_entry AS entry
                WHERE entry.kind = 'pi.assistant'
                  AND entry.by_run_id IS NOT NULL
                  AND jsonb_typeof(entry.data->'usage') = 'object'
            ),
            per_run AS (
                SELECT
                    run_id,
                    count(*)::bigint AS api_calls,
                    COALESCE(sum(prompt_tokens), 0)::bigint AS prompt_tokens,
                    COALESCE(sum(completion_tokens), 0)::bigint AS completion_tokens,
                    COALESCE(sum(total_tokens), 0)::bigint AS total_tokens,
                    COALESCE(sum(cached_tokens), 0)::bigint AS cached_tokens
                FROM assistant_usage
                GROUP BY run_id
            )
            UPDATE agent_run AS run
            SET prompt_tokens = per_run.prompt_tokens,
                completion_tokens = per_run.completion_tokens,
                total_tokens = per_run.total_tokens,
                cached_tokens = per_run.cached_tokens,
                api_calls = per_run.api_calls
            FROM per_run
            WHERE run.id = per_run.run_id
            """
        )
    )


def _backfill_accounts() -> None:
    op.execute(
        sa.text(
            """
            WITH per_user AS (
                SELECT
                    user_id,
                    COALESCE(sum(prompt_tokens), 0)::bigint AS prompt_tokens,
                    COALESCE(sum(completion_tokens), 0)::bigint AS completion_tokens,
                    COALESCE(sum(total_tokens), 0)::bigint AS total_tokens,
                    COALESCE(sum(cached_tokens), 0)::bigint AS cached_tokens,
                    COALESCE(sum(api_calls), 0)::bigint AS api_calls,
                    count(*)::bigint AS agent_turns,
                    max(created_at) AS last_agent_activity_at
                FROM agent_run
                GROUP BY user_id
            )
            UPDATE app_user AS account
            SET prompt_tokens = per_user.prompt_tokens,
                completion_tokens = per_user.completion_tokens,
                total_tokens = per_user.total_tokens,
                cached_tokens = per_user.cached_tokens,
                api_calls = per_user.api_calls,
                agent_turns = per_user.agent_turns,
                last_agent_activity_at = per_user.last_agent_activity_at
            FROM per_user
            WHERE account.id = per_user.user_id
            """
        )
    )


def _create_usage_rollup_trigger() -> None:
    op.execute(
        """
        CREATE OR REPLACE FUNCTION agent_run_apply_usage_delta()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            IF TG_OP = 'INSERT' THEN
                UPDATE app_user
                SET prompt_tokens = prompt_tokens + NEW.prompt_tokens,
                    completion_tokens = completion_tokens + NEW.completion_tokens,
                    total_tokens = total_tokens + NEW.total_tokens,
                    cached_tokens = cached_tokens + NEW.cached_tokens,
                    api_calls = api_calls + NEW.api_calls,
                    agent_turns = agent_turns + 1,
                    last_agent_activity_at = GREATEST(
                        COALESCE(last_agent_activity_at, NEW.created_at),
                        NEW.created_at
                    )
                WHERE id = NEW.user_id;
                RETURN NEW;
            END IF;

            IF TG_OP = 'UPDATE' THEN
                IF NEW.user_id = OLD.user_id
                   AND NEW.prompt_tokens = OLD.prompt_tokens
                   AND NEW.completion_tokens = OLD.completion_tokens
                   AND NEW.total_tokens = OLD.total_tokens
                   AND NEW.cached_tokens = OLD.cached_tokens
                   AND NEW.api_calls = OLD.api_calls THEN
                    RETURN NEW;
                END IF;

                IF NEW.user_id = OLD.user_id THEN
                    UPDATE app_user
                    SET prompt_tokens = GREATEST(
                            0, prompt_tokens + (NEW.prompt_tokens - OLD.prompt_tokens)
                        ),
                        completion_tokens = GREATEST(
                            0, completion_tokens + (NEW.completion_tokens - OLD.completion_tokens)
                        ),
                        total_tokens = GREATEST(
                            0, total_tokens + (NEW.total_tokens - OLD.total_tokens)
                        ),
                        cached_tokens = GREATEST(
                            0, cached_tokens + (NEW.cached_tokens - OLD.cached_tokens)
                        ),
                        api_calls = GREATEST(
                            0, api_calls + (NEW.api_calls - OLD.api_calls)
                        )
                    WHERE id = NEW.user_id;
                ELSE
                    UPDATE app_user
                    SET prompt_tokens = GREATEST(0, prompt_tokens - OLD.prompt_tokens),
                        completion_tokens = GREATEST(0, completion_tokens - OLD.completion_tokens),
                        total_tokens = GREATEST(0, total_tokens - OLD.total_tokens),
                        cached_tokens = GREATEST(0, cached_tokens - OLD.cached_tokens),
                        api_calls = GREATEST(0, api_calls - OLD.api_calls),
                        agent_turns = GREATEST(0, agent_turns - 1),
                        last_agent_activity_at = (
                            SELECT max(run.created_at)
                            FROM agent_run AS run
                            WHERE run.user_id = OLD.user_id
                        )
                    WHERE id = OLD.user_id;

                    UPDATE app_user
                    SET prompt_tokens = prompt_tokens + NEW.prompt_tokens,
                        completion_tokens = completion_tokens + NEW.completion_tokens,
                        total_tokens = total_tokens + NEW.total_tokens,
                        cached_tokens = cached_tokens + NEW.cached_tokens,
                        api_calls = api_calls + NEW.api_calls,
                        agent_turns = agent_turns + 1,
                        last_agent_activity_at = (
                            SELECT max(run.created_at)
                            FROM agent_run AS run
                            WHERE run.user_id = NEW.user_id
                        )
                    WHERE id = NEW.user_id;
                END IF;
                RETURN NEW;
            END IF;

            UPDATE app_user
            SET prompt_tokens = GREATEST(0, prompt_tokens - OLD.prompt_tokens),
                completion_tokens = GREATEST(0, completion_tokens - OLD.completion_tokens),
                total_tokens = GREATEST(0, total_tokens - OLD.total_tokens),
                cached_tokens = GREATEST(0, cached_tokens - OLD.cached_tokens),
                api_calls = GREATEST(0, api_calls - OLD.api_calls),
                agent_turns = GREATEST(0, agent_turns - 1),
                last_agent_activity_at = (
                    SELECT max(run.created_at)
                    FROM agent_run AS run
                    WHERE run.user_id = OLD.user_id
                )
            WHERE id = OLD.user_id;
            RETURN OLD;
        END;
        $$;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_agent_run_usage_rollup
        AFTER INSERT OR UPDATE OR DELETE ON agent_run
        FOR EACH ROW EXECUTE FUNCTION agent_run_apply_usage_delta();
        """
    )


def upgrade() -> None:
    _assert_migration_role_can_bypass_rls()

    for column in _USAGE_COLUMNS:
        op.add_column(
            "agent_run",
            sa.Column(
                column,
                sa.Integer() if column == "api_calls" else sa.BigInteger(),
                server_default=sa.text("0"),
                nullable=False,
            ),
        )
    op.create_check_constraint(
        op.f("ck_agent_run_usage_non_negative"),
        "agent_run",
        "prompt_tokens >= 0 AND completion_tokens >= 0 AND total_tokens >= 0 "
        "AND cached_tokens >= 0 AND api_calls >= 0",
    )

    for column in _USAGE_COLUMNS:
        op.add_column(
            "app_user",
            sa.Column(
                column,
                sa.BigInteger(),
                server_default=sa.text("0"),
                nullable=False,
            ),
        )
    op.add_column(
        "app_user",
        sa.Column(
            "agent_turns",
            sa.BigInteger(),
            server_default=sa.text("0"),
            nullable=False,
        ),
    )
    op.add_column(
        "app_user",
        sa.Column("last_agent_activity_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_check_constraint(
        op.f("ck_app_user_usage_non_negative"),
        "app_user",
        "prompt_tokens >= 0 AND completion_tokens >= 0 AND total_tokens >= 0 "
        "AND cached_tokens >= 0 AND api_calls >= 0 AND agent_turns >= 0",
    )

    op.add_column(
        "user_session",
        sa.Column("impersonator_user_id", sa.BigInteger(), nullable=True),
    )
    op.create_foreign_key(
        op.f("fk_user_session_impersonator_user_id_app_user"),
        "user_session",
        "app_user",
        ["impersonator_user_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index(
        "ix_user_session_impersonator_user_id",
        "user_session",
        ["impersonator_user_id"],
        unique=False,
    )

    # Backfill before creating the trigger; otherwise the historical rows would
    # be counted once by the trigger and again by the denominator update.
    _backfill_agent_runs()
    _backfill_accounts()
    _create_usage_rollup_trigger()


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_agent_run_usage_rollup ON agent_run")
    op.execute("DROP FUNCTION IF EXISTS agent_run_apply_usage_delta()")

    op.drop_index("ix_user_session_impersonator_user_id", table_name="user_session")
    op.drop_constraint(
        op.f("fk_user_session_impersonator_user_id_app_user"),
        "user_session",
        type_="foreignkey",
    )
    op.drop_column("user_session", "impersonator_user_id")

    op.drop_constraint(
        op.f("ck_app_user_usage_non_negative"),
        "app_user",
        type_="check",
    )
    op.drop_column("app_user", "last_agent_activity_at")
    op.drop_column("app_user", "agent_turns")
    for column in reversed(_USAGE_COLUMNS):
        op.drop_column("app_user", column)

    op.drop_constraint(
        op.f("ck_agent_run_usage_non_negative"),
        "agent_run",
        type_="check",
    )
    for column in reversed(_USAGE_COLUMNS):
        op.drop_column("agent_run", column)
