"""Companion memories gain weights instead of locks; replies record their speaker.

Revision ID: d6a1f3c8e2b7
Revises: e7b2d5a9c4f1
Create Date: 2026-11-28 18:00:00

The librarian's memories were gated by tiers that unlocked after a number of
completed runs. The tiers become a ``weight`` she can see and judge for herself:
``first`` → ``everyday``, ``familiar`` → ``past``, ``rare`` → ``heart``. The
unlock counters and unlock timestamps are removed; ``companion_bond`` keeps the
run and conversation counts and gains ``first_met_at`` so the librarian knows
how long the two of them have known each other.

- ``tier`` → ``weight`` on ``companion_lore_fragment``, ``companion_lore_item``,
  ``companion_generated_story``, and ``companion_admin_lore_override``.
- ``life_story_tier`` → ``life_story_weight`` on ``companion_config`` and
  ``companion_user_config``; the ``*_unlock_runs`` knobs are dropped.
- ``companion_bond``: drop ``familiar_unlocked_at`` / ``rare_unlocked_at``, add
  ``first_met_at`` (backfilled from the first conversation frozen to that
  companion).
- ``companion_lore_told.source`` also accepts ``'recall'`` (the librarian looked
  a memory up with ``recall_my_memories``).
- ``agent_entry``: every existing assistant entry whose conversation froze a
  companion gets ``data.speaker = {ref, name}``, so past replies can be
  attributed. New replies are stamped when they are written.

No policy or grant changes: every table keeps its existing row-level security.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "d6a1f3c8e2b7"
down_revision: str | None = "e7b2d5a9c4f1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

WEIGHTS = "'everyday', 'past', 'heart'"
TIERS = "'first', 'familiar', 'rare'"
TO_WEIGHT = (
    "CASE {col} WHEN 'first' THEN 'everyday' WHEN 'familiar' THEN 'past' "
    "WHEN 'rare' THEN 'heart' ELSE {col} END"
)
TO_TIER = (
    "CASE {col} WHEN 'everyday' THEN 'first' WHEN 'past' THEN 'familiar' "
    "WHEN 'heart' THEN 'rare' ELSE {col} END"
)

# (table, old column, new column, nullable, old check name, new check name)
_RENAMES: tuple[tuple[str, str, str, bool], ...] = (
    ("companion_lore_fragment", "tier", "weight", False),
    ("companion_lore_item", "tier", "weight", False),
    ("companion_generated_story", "tier", "weight", False),
    ("companion_admin_lore_override", "tier", "weight", True),
    ("companion_config", "life_story_tier", "life_story_weight", False),
    ("companion_user_config", "life_story_tier", "life_story_weight", True),
)


BACKFILL_SPEAKERS_SQL = """
        UPDATE agent_entry AS reply
        SET data = COALESCE(
                CASE WHEN jsonb_typeof(reply.data) = 'object' THEN reply.data END,
                '{}'::jsonb
            ) || jsonb_build_object(
                'speaker',
                jsonb_build_object(
                    'ref', frozen.data -> 'companion' ->> 'ref',
                    'name', COALESCE(frozen.data -> 'companion' ->> 'name', '')
                )
            )
        FROM (
            SELECT DISTINCT ON (conversation_id) conversation_id, data
            FROM agent_entry
            WHERE kind = 'pi.system'
            ORDER BY conversation_id, id
        ) AS frozen
        WHERE reply.kind = 'pi.assistant'
          AND reply.conversation_id = frozen.conversation_id
          AND jsonb_typeof(frozen.data) = 'object'
          AND frozen.data -> 'companion' ->> 'ref' IS NOT NULL
          AND (jsonb_typeof(reply.data) IS DISTINCT FROM 'object' OR NOT reply.data ? 'speaker')
        """


def _check(column: str, values: str, nullable: bool) -> str:
    clause = f"{column} IN ({values})"
    return f"{column} IS NULL OR {clause}" if nullable else clause


def _rename(old: str, new: str, values: str, mapping: str) -> None:
    for table, old_col, new_col, nullable in _RENAMES:
        source = old_col if old == "tier" else new_col
        target = new_col if old == "tier" else old_col
        op.drop_constraint(op.f(f"ck_{table}_{source}_valid"), table, type_="check")
        op.alter_column(table, source, new_column_name=target)
        op.execute(f"UPDATE {table} SET {target} = {mapping.format(col=target)}")
        op.create_check_constraint(
            op.f(f"ck_{table}_{target}_valid"),
            table,
            _check(target, values, nullable),
        )


def upgrade() -> None:
    _rename("tier", "weight", WEIGHTS, TO_WEIGHT)
    op.alter_column("companion_config", "life_story_weight", server_default="past")

    for table in ("companion_config", "companion_user_config"):
        op.drop_constraint(op.f(f"ck_{table}_rare_unlock_runs_range"), table, type_="check")
        op.drop_constraint(op.f(f"ck_{table}_familiar_unlock_runs_range"), table, type_="check")
        op.drop_column(table, "rare_unlock_runs")
        op.drop_column(table, "familiar_unlock_runs")

    op.drop_column("companion_bond", "rare_unlocked_at")
    op.drop_column("companion_bond", "familiar_unlocked_at")
    op.add_column(
        "companion_bond",
        sa.Column("first_met_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.execute(
        """
        UPDATE companion_bond AS bond
        SET first_met_at = met.first_at
        FROM (
            SELECT entry.user_id,
                   entry.data -> 'companion' ->> 'ref' AS ref,
                   min(entry.created_at) AS first_at
            FROM agent_entry AS entry
            WHERE entry.kind = 'pi.system'
              AND jsonb_typeof(entry.data) = 'object'
              AND entry.data -> 'companion' ->> 'ref' IS NOT NULL
            GROUP BY entry.user_id, entry.data -> 'companion' ->> 'ref'
        ) AS met
        WHERE bond.user_id = met.user_id AND bond.companion_ref = met.ref
        """
    )
    op.execute("UPDATE companion_bond SET first_met_at = updated_at WHERE first_met_at IS NULL")

    op.drop_constraint(
        op.f("ck_companion_lore_told_source_valid"),
        "companion_lore_told",
        type_="check",
    )
    op.create_check_constraint(
        op.f("ck_companion_lore_told_source_valid"),
        "companion_lore_told",
        "source IN ('topical', 'story_moment', 'self_query', 'admin', 'recall')",
    )

    # Attribute every past reply to the companion its conversation froze.
    op.execute(BACKFILL_SPEAKERS_SQL)


def downgrade() -> None:
    op.execute(
        """
        UPDATE agent_entry SET data = data - 'speaker'
        WHERE kind = 'pi.assistant' AND jsonb_typeof(data) = 'object' AND data ? 'speaker'
        """
    )
    op.execute("DELETE FROM companion_lore_told WHERE source = 'recall'")
    op.drop_constraint(
        op.f("ck_companion_lore_told_source_valid"),
        "companion_lore_told",
        type_="check",
    )
    op.create_check_constraint(
        op.f("ck_companion_lore_told_source_valid"),
        "companion_lore_told",
        "source IN ('topical', 'story_moment', 'self_query', 'admin')",
    )

    op.drop_column("companion_bond", "first_met_at")
    op.add_column(
        "companion_bond",
        sa.Column("familiar_unlocked_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "companion_bond",
        sa.Column("rare_unlocked_at", sa.DateTime(timezone=True), nullable=True),
    )

    for table, nullable in (("companion_config", False), ("companion_user_config", True)):
        op.add_column(
            table,
            sa.Column(
                "familiar_unlock_runs",
                sa.Integer(),
                nullable=nullable,
                server_default=None if nullable else sa.text("5"),
            ),
        )
        op.add_column(
            table,
            sa.Column(
                "rare_unlock_runs",
                sa.Integer(),
                nullable=nullable,
                server_default=None if nullable else sa.text("20"),
            ),
        )
    op.create_check_constraint(
        op.f("ck_companion_config_familiar_unlock_runs_range"),
        "companion_config",
        "familiar_unlock_runs BETWEEN 0 AND 1000",
    )
    op.create_check_constraint(
        op.f("ck_companion_config_rare_unlock_runs_range"),
        "companion_config",
        "rare_unlock_runs BETWEEN 0 AND 10000 AND rare_unlock_runs >= familiar_unlock_runs",
    )
    op.create_check_constraint(
        op.f("ck_companion_user_config_familiar_unlock_runs_range"),
        "companion_user_config",
        "familiar_unlock_runs IS NULL OR familiar_unlock_runs BETWEEN 0 AND 1000",
    )
    op.create_check_constraint(
        op.f("ck_companion_user_config_rare_unlock_runs_range"),
        "companion_user_config",
        "rare_unlock_runs IS NULL OR rare_unlock_runs BETWEEN 0 AND 10000",
    )

    op.alter_column("companion_config", "life_story_weight", server_default="familiar")
    _rename("weight", "tier", TIERS, TO_TIER)
