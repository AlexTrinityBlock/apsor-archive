"""Advisory metadata for model names used by endpoint assignments.

The catalog is deliberately **not** an allow-list. A model name is free text;
any string outside this table is legal, pinned (``tier=None`` means no
escalation), unpriced, and estimated at the default character density. This
module only supplies the hints a cost readout, a settings panel, and the token
estimator need.

Prices are USD per million tokens. ``suggested_compaction_tokens`` is a UI
prefill, never a ceiling; the operator-owned budget remains authoritative.
"""

from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

ModelTier = Literal["economy", "standard", "premium", "frontier"]
ModelStatus = Literal["current", "previous", "deprecated"]

TaskClass = Literal[
    "agent_chat",
    "web_research",
    "summary",
    "memory",
    "classification",
    "extraction",
    "vision",
]

# Tasks that background/auxiliary work performs. Dispatch itself is slot-based;
# this set only labels accounting and, historically, cheap-model routing.
AUXILIARY_TASKS: frozenset[TaskClass] = frozenset(
    {"summary", "memory", "classification", "extraction", "vision"}
)

# Cheapest to most expensive. Escalation walks one step to the right.
TIER_ORDER: tuple[ModelTier, ...] = ("economy", "standard", "premium", "frontier")

# Unknown model names are estimated with the same density as Claude rows.
DEFAULT_CHARS_PER_TOKEN = 2.3


@dataclass(frozen=True)
class ModelPrices:
    """USD per million tokens; ``cache_write`` is the 5-minute write bucket."""

    input: Decimal
    output: Decimal
    cache_write: Decimal
    cache_read: Decimal


@dataclass(frozen=True)
class ModelSpec:
    """One advisory catalog row.

    A missing catalog row is equivalent to ``tier=None``, ``prices=None``,
    ``suggested_compaction_tokens=None``, and ``chars_per_token=2.3``; callers
    should use :func:`spec_for` / :func:`chars_per_token_for` rather than
    indexing the table directly.
    """

    model: str
    display_name: str
    provider: str
    tier: ModelTier | None
    context_window_tokens: int
    max_output_tokens: int
    prices: ModelPrices | None
    chars_per_token: float
    supports_tools: bool
    supports_vision: bool
    suggested_compaction_tokens: int | None
    long_prompt_threshold_tokens: int | None = None
    long_prompt_multiplier: Decimal | None = None
    status: ModelStatus = "current"
    replacement_model: str | None = None


MODEL_CATALOG: dict[str, ModelSpec] = {
    "claude-haiku-5-5": ModelSpec(
        model="claude-haiku-5-5",
        display_name="Claude Haiku 5.5",
        provider="anthropic",
        tier="economy",
        context_window_tokens=1_000_000,
        max_output_tokens=128_000,
        prices=ModelPrices(
            input=Decimal("0.10"),
            output=Decimal("0.50"),
            cache_write=Decimal("0.125"),
            cache_read=Decimal("0.01"),
        ),
        chars_per_token=2.3,
        supports_tools=True,
        supports_vision=True,
        suggested_compaction_tokens=90_000,
        status="current",
        long_prompt_threshold_tokens=100_000,
        long_prompt_multiplier=Decimal("5"),
    ),
    "claude-sonnet-5-5": ModelSpec(
        model="claude-sonnet-5-5",
        display_name="Claude Sonnet 5.5",
        provider="anthropic",
        tier="standard",
        context_window_tokens=1_000_000,
        max_output_tokens=128_000,
        prices=ModelPrices(
            input=Decimal("2.00"),
            output=Decimal("10.00"),
            cache_write=Decimal("2.50"),
            cache_read=Decimal("0.10"),
        ),
        chars_per_token=2.3,
        supports_tools=True,
        supports_vision=True,
        suggested_compaction_tokens=850_000,
        status="current",
    ),
    "claude-opus-5-5": ModelSpec(
        model="claude-opus-5-5",
        display_name="Claude Opus 5.5",
        provider="anthropic",
        tier="premium",
        context_window_tokens=1_000_000,
        max_output_tokens=128_000,
        prices=ModelPrices(
            input=Decimal("4.00"),
            output=Decimal("20.00"),
            cache_write=Decimal("5.00"),
            cache_read=Decimal("0.20"),
        ),
        chars_per_token=2.3,
        supports_tools=True,
        supports_vision=True,
        suggested_compaction_tokens=850_000,
        status="current",
    ),
    "claude-fable-5-2": ModelSpec(
        model="claude-fable-5-2",
        display_name="Claude Fable 5.2",
        provider="anthropic",
        tier="frontier",
        context_window_tokens=1_000_000,
        max_output_tokens=128_000,
        prices=ModelPrices(
            input=Decimal("8.00"),
            output=Decimal("40.00"),
            cache_write=Decimal("10.00"),
            cache_read=Decimal("0.20"),
        ),
        chars_per_token=2.3,
        supports_tools=True,
        supports_vision=True,
        suggested_compaction_tokens=850_000,
        status="current",
    ),
    "claude-haiku-4-5": ModelSpec(
        model="claude-haiku-4-5",
        display_name="Claude Haiku 4.5",
        provider="anthropic",
        tier="economy",
        context_window_tokens=200_000,
        max_output_tokens=64_000,
        prices=ModelPrices(
            input=Decimal("1.00"),
            output=Decimal("5.00"),
            cache_write=Decimal("1.25"),
            cache_read=Decimal("0.10"),
        ),
        chars_per_token=2.3,
        supports_tools=True,
        supports_vision=True,
        suggested_compaction_tokens=150_000,
        status="previous",
        replacement_model="claude-haiku-5-5",
    ),
    "deepseek-flash": ModelSpec(
        model="deepseek-flash",
        display_name="DeepSeek Flash",
        provider="deepseek",
        tier="economy",
        context_window_tokens=1_000_000,
        max_output_tokens=384_000,
        prices=None,
        chars_per_token=3.0,
        supports_tools=True,
        supports_vision=True,
        suggested_compaction_tokens=75_000,
        status="current",
    ),
}


def spec_for(model: str) -> ModelSpec | None:
    """Return the advisory row for ``model``, or ``None`` when it is unknown."""
    return MODEL_CATALOG.get(model)


def chars_per_token_for(model: str) -> float:
    """Return the model's estimation density, or the 2.3 default when unknown."""
    spec = spec_for(model)
    return spec.chars_per_token if spec is not None else DEFAULT_CHARS_PER_TOKEN


__all__ = [
    "AUXILIARY_TASKS",
    "DEFAULT_CHARS_PER_TOKEN",
    "MODEL_CATALOG",
    "TIER_ORDER",
    "ModelPrices",
    "ModelSpec",
    "ModelStatus",
    "ModelTier",
    "TaskClass",
    "chars_per_token_for",
    "spec_for",
]
