"""Per-account chat endpoint resolution.

Every account owns two endpoint assignments: a primary for agent chat and an
auxiliary for summaries, memory, ingest extraction, and vision. This module is
the only resolver. It reads the assignment from ``app_user`` (an auth table
outside row-level security), maps a slot to one exact ``chat_provider_config``
row by id, and builds a generator from that row alone.

Two rules are deliberate:

* There is **no fallback**. A missing, inactive, disabled, or keyless endpoint
  yields :class:`NullTextGenerator`; ``runtime.chat_config`` and the deployment
  environment key are never consulted to rescue a user call.
* The auxiliary slot inherits the primary row id and model **only** when both
  auxiliary assignment fields are NULL. That is the Q1 backfill shape, not a
  provider fallback: the row is still the primary endpoint, and the auxiliary
  effort (``low`` by default) keeps background work cheap.
"""

import hashlib
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.ai.deepseek_client import NullTextGenerator
from app.infrastructure.ai.runtime import AiRuntime
from app.module.auth.model.auth_model import AppUserModel
from app.module.knowledge.protocol.provider_config import ProviderConfig
from app.module.knowledge.protocol.text_generator_protocol import TextGeneratorProtocol

AssignmentSlot = Literal["primary", "auxiliary"]

# The auxiliary effort column is NOT NULL, but a legacy row may still contain
# an empty string; resolution normalises it rather than sending an empty
# parameter to a provider.
DEFAULT_AUXILIARY_EFFORT = "low"


@dataclass(frozen=True)
class ChatAssignment:
    """The eight stored assignment columns for one account."""

    user_id: int
    provider_config_id: int | None
    model: str | None
    reasoning_effort: str | None
    aux_provider_config_id: int | None
    aux_model: str | None
    aux_reasoning_effort: str
    context_window_tokens: int | None
    compaction_threshold_tokens: int | None


@dataclass(frozen=True)
class SlotValues:
    """One slot after inheritance, before endpoint resolution.

    ``inherited`` is true only for the Q1 shape where both auxiliary fields are
    NULL and the primary pair stands in. It is reported so the assignment read
    surface can emit the ``aux_inherited_from_primary`` warning.
    """

    row_id: int | None
    model: str | None
    effort: str | None
    inherited: bool = False


@dataclass(frozen=True)
class UserGenerator:
    """A generator built for one account slot.

    ``provider`` is ``"none"`` whenever the generator is the null implementation,
    so a caller can distinguish "no working endpoint" from a real provider
    without inspecting the client.
    """

    generator: TextGeneratorProtocol
    model: str
    provider: str
    effort: str | None
    provider_config_id: int | None


async def load_assignment(session: AsyncSession, user_id: int) -> ChatAssignment:
    """Load both slots in one SELECT over the eight ``app_user`` columns.

    ``app_user`` has no row-level security, so this read works from the agent's
    system session and from the owner session the knowledge builders already
    hold. The caller supplies the captured ``user_id``; it never comes from a
    request body. A missing account resolves to an unassigned value object
    rather than raising: the user paths treat that exactly like "no model
    assigned", and a deleted account cannot reach them through authentication.
    """
    row = (
        await session.execute(
            select(
                AppUserModel.chat_provider_config_id,
                AppUserModel.chat_model,
                AppUserModel.chat_reasoning_effort,
                AppUserModel.aux_provider_config_id,
                AppUserModel.aux_model,
                AppUserModel.aux_reasoning_effort,
                AppUserModel.chat_context_window_tokens,
                AppUserModel.chat_compaction_threshold_tokens,
            ).where(AppUserModel.id == user_id)
        )
    ).one_or_none()
    if row is None:
        return ChatAssignment(
            user_id=user_id,
            provider_config_id=None,
            model=None,
            reasoning_effort=None,
            aux_provider_config_id=None,
            aux_model=None,
            aux_reasoning_effort=DEFAULT_AUXILIARY_EFFORT,
            context_window_tokens=None,
            compaction_threshold_tokens=None,
        )
    (
        provider_config_id,
        model,
        reasoning_effort,
        aux_provider_config_id,
        aux_model,
        aux_reasoning_effort,
        context_window_tokens,
        compaction_threshold_tokens,
    ) = row
    return ChatAssignment(
        user_id=user_id,
        provider_config_id=provider_config_id,
        model=model,
        reasoning_effort=reasoning_effort,
        aux_provider_config_id=aux_provider_config_id,
        aux_model=aux_model,
        aux_reasoning_effort=aux_reasoning_effort or DEFAULT_AUXILIARY_EFFORT,
        context_window_tokens=context_window_tokens,
        compaction_threshold_tokens=compaction_threshold_tokens,
    )


def resolve_endpoint(
    chain: Sequence[ProviderConfig],
    row_id: int,
) -> ProviderConfig | None:
    """Return the chain entry whose database row id is ``row_id``.

    ``runtime.chat_chain`` carries active rows in ``(priority, id)`` order.
    Environment and default fallbacks keep ``row_id=None``, so a row-id lookup
    can never match one of them; that is the mechanical guarantee that no
    account is ever served by the deployment key.
    """
    return next((config for config in chain if config.row_id == row_id), None)


def slot_values(assignment: ChatAssignment, slot: AssignmentSlot) -> SlotValues:
    """Return one slot's row id, model, and effort after inheritance.

    The primary slot never inherits. The auxiliary slot inherits the primary row
    id and model only when both ``aux_provider_config_id`` and ``aux_model`` are
    NULL; a NULL row with a non-NULL model means the endpoint row was deleted,
    and the slot is broken rather than inherited.
    """
    if slot == "primary":
        return SlotValues(
            row_id=assignment.provider_config_id,
            model=assignment.model,
            effort=assignment.reasoning_effort,
        )
    effort = assignment.aux_reasoning_effort or DEFAULT_AUXILIARY_EFFORT
    if assignment.aux_provider_config_id is None and assignment.aux_model is None:
        return SlotValues(
            row_id=assignment.provider_config_id,
            model=assignment.model,
            effort=effort,
            inherited=True,
        )
    return SlotValues(
        row_id=assignment.aux_provider_config_id,
        model=assignment.aux_model,
        effort=effort,
    )


def build_user_text_generator(
    runtime: AiRuntime,
    assignment: ChatAssignment,
    *,
    slot: AssignmentSlot,
) -> UserGenerator:
    """Build the generator for one slot, or a null generator.

    The endpoint is resolved strictly by row id from the runtime chain. Missing,
    inactive (not in the chain), ``provider == "none"``, and keyless endpoints
    all yield :class:`NullTextGenerator`. The code never retries another row and
    never falls back to ``runtime.chat_config``.

    A successful build derives a frozen copy with the assigned model and effort;
    the shared endpoint row itself never stores either value.
    """
    values = slot_values(assignment, slot)
    model = values.model
    effort = values.effort
    if values.row_id is None or not model:
        return UserGenerator(
            generator=NullTextGenerator(),
            model=model or "",
            provider="none",
            effort=effort,
            provider_config_id=None,
        )
    resolved = resolve_endpoint(runtime.chat_chain, values.row_id)
    if (
        resolved is None
        or not resolved.enabled
        or resolved.provider == "none"
        or not resolved.api_key
    ):
        return UserGenerator(
            generator=NullTextGenerator(),
            model=model,
            provider="none",
            effort=effort,
            provider_config_id=values.row_id,
        )
    config = resolved.model_copy(update={"model": model, "reasoning_effort": effort})
    return UserGenerator(
        generator=runtime.builder.build_text_generator(config),
        model=model,
        provider=config.provider,
        effort=effort,
        provider_config_id=values.row_id,
    )


def assignment_fingerprint(
    row: ProviderConfig,
    model: str,
    effort: str | None,
    *,
    api_key_ciphertext: str = "",
) -> str:
    """Hash the parts of a slot that change the wire connection.

    One value per line, in order: the endpoint row id, provider, base URL,
    ``sha256(api_key_ciphertext or "")``, model, and effort. ``label``,
    ``priority``, ``is_active``, ``updated_at``, ``max_output_tokens``, and the
    budget columns are excluded because they do not change the connection.

    ``ProviderConfig`` carries the **decrypted** key, never the stored
    ciphertext, so callers that hold the database row must pass
    ``api_key_ciphertext=row.api_key_ciphertext or ""``. The assignment save
    gate does exactly that on both the stored and the incoming side, which keeps
    the comparison consistent and makes a rotated key visible in the computed
    value instead of hashing the plaintext. No fingerprint is persisted, so the
    gate compares two values computed from the current rows; a key-only rotation
    therefore does not by itself force a re-probe, and the provider dialog's own
    Test covers that rotation. The default hashes the empty string and therefore
    describes a keyless endpoint; the plaintext key is never hashed, returned, or
    logged.
    """
    parts = (
        "" if row.row_id is None else str(row.row_id),
        row.provider,
        row.base_url or "",
        hashlib.sha256(api_key_ciphertext.encode("utf-8")).hexdigest(),
        model,
        effort or "",
    )
    return hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()


__all__ = [
    "DEFAULT_AUXILIARY_EFFORT",
    "AssignmentSlot",
    "ChatAssignment",
    "SlotValues",
    "UserGenerator",
    "assignment_fingerprint",
    "build_user_text_generator",
    "load_assignment",
    "resolve_endpoint",
    "slot_values",
]
