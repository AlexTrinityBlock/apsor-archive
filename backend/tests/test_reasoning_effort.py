"""Advisory model metadata and reasoning-effort catalog contracts.

These cases are pure data checks: no database, no provider, and no import of
the application runtime. The catalog is advisory, so unknown names must stay
legal and unpriced instead of failing validation.
"""

from dataclasses import FrozenInstanceError
from decimal import Decimal
from typing import get_args

import pytest

from app.infrastructure.ai.model_catalog import (
    AUXILIARY_TASKS,
    DEFAULT_CHARS_PER_TOKEN,
    MODEL_CATALOG,
    TIER_ORDER,
    ModelPrices,
    ModelSpec,
    TaskClass,
    chars_per_token_for,
    spec_for,
)


def test_catalog_contains_exactly_the_verified_rows() -> None:
    assert set(MODEL_CATALOG) == {
        "claude-haiku-5-5",
        "claude-sonnet-5-5",
        "claude-opus-5-5",
        "claude-fable-5-2",
        "claude-haiku-4-5",
        "deepseek-flash",
    }


@pytest.mark.parametrize(
    ("model", "tier", "context_window", "max_output", "suggested_trigger"),
    [
        ("claude-haiku-5-5", "economy", 1_000_000, 128_000, 90_000),
        ("claude-sonnet-5-5", "standard", 1_000_000, 128_000, 850_000),
        ("claude-opus-5-5", "premium", 1_000_000, 128_000, 850_000),
        ("claude-fable-5-2", "frontier", 1_000_000, 128_000, 850_000),
        ("claude-haiku-4-5", "economy", 200_000, 64_000, 150_000),
        ("deepseek-flash", "economy", 1_000_000, 384_000, 75_000),
    ],
)
def test_catalog_rows_match_the_design_table(
    model: str,
    tier: str,
    context_window: int,
    max_output: int,
    suggested_trigger: int,
) -> None:
    spec = MODEL_CATALOG[model]
    assert spec.model == model
    assert spec.tier == tier
    assert spec.context_window_tokens == context_window
    assert spec.max_output_tokens == max_output
    assert spec.suggested_compaction_tokens == suggested_trigger
    assert spec.supports_tools is True
    assert spec.supports_vision is True


@pytest.mark.parametrize(
    ("model", "prices"),
    [
        (
            "claude-haiku-5-5",
            ("0.10", "0.50", "0.125", "0.01"),
        ),
        (
            "claude-sonnet-5-5",
            ("2.00", "10.00", "2.50", "0.10"),
        ),
        (
            "claude-opus-5-5",
            ("4.00", "20.00", "5.00", "0.20"),
        ),
        (
            "claude-fable-5-2",
            ("8.00", "40.00", "10.00", "0.20"),
        ),
        (
            "claude-haiku-4-5",
            ("1.00", "5.00", "1.25", "0.10"),
        ),
    ],
)
def test_catalog_prices_match_the_design_table(
    model: str,
    prices: tuple[str, str, str, str],
) -> None:
    spec = MODEL_CATALOG[model]
    assert spec.prices == ModelPrices(
        input=Decimal(prices[0]),
        output=Decimal(prices[1]),
        cache_write=Decimal(prices[2]),
        cache_read=Decimal(prices[3]),
    )


def test_deepseek_flash_is_priced_as_none() -> None:
    spec = MODEL_CATALOG["deepseek-flash"]
    assert spec.prices is None
    assert spec.chars_per_token == 3.0
    assert spec.replacement_model is None


def test_unknown_model_is_legal_and_unpriced() -> None:
    assert spec_for("claude-unknown-9") is None
    assert MODEL_CATALOG.get("claude-unknown-9") is None
    assert chars_per_token_for("claude-unknown-9") == DEFAULT_CHARS_PER_TOKEN
    assert DEFAULT_CHARS_PER_TOKEN == 2.3


def test_chars_per_token_for_known_models() -> None:
    assert chars_per_token_for("claude-haiku-5-5") == 2.3
    assert chars_per_token_for("claude-sonnet-5-5") == 2.3
    assert chars_per_token_for("claude-haiku-4-5") == 2.3
    assert chars_per_token_for("deepseek-flash") == 3.0


def test_haiku_five_five_has_the_long_prompt_surcharge_fields() -> None:
    spec = MODEL_CATALOG["claude-haiku-5-5"]
    assert spec.long_prompt_threshold_tokens == 100_000
    assert spec.long_prompt_multiplier == Decimal("5")


@pytest.mark.parametrize(
    "model",
    [
        "claude-sonnet-5-5",
        "claude-opus-5-5",
        "claude-fable-5-2",
        "claude-haiku-4-5",
        "deepseek-flash",
    ],
)
def test_other_rows_have_no_long_prompt_surcharge(model: str) -> None:
    spec = MODEL_CATALOG[model]
    assert spec.long_prompt_threshold_tokens is None
    assert spec.long_prompt_multiplier is None


def test_previous_generation_row_names_its_replacement() -> None:
    spec = MODEL_CATALOG["claude-haiku-4-5"]
    assert spec.status == "previous"
    assert spec.replacement_model == "claude-haiku-5-5"
    assert MODEL_CATALOG["claude-haiku-5-5"].status == "current"


def test_task_class_and_auxiliary_tasks() -> None:
    task_values = set(get_args(TaskClass))
    assert task_values == {
        "agent_chat",
        "web_research",
        "summary",
        "memory",
        "classification",
        "extraction",
        "vision",
    }
    assert AUXILIARY_TASKS <= task_values
    assert AUXILIARY_TASKS == {"summary", "memory", "classification", "extraction", "vision"}
    assert "agent_chat" not in AUXILIARY_TASKS


def test_tier_order_walks_from_cheapest_to_most_expensive() -> None:
    assert TIER_ORDER == ("economy", "standard", "premium", "frontier")


def test_catalog_specs_are_frozen() -> None:
    spec = MODEL_CATALOG["claude-haiku-5-5"]
    assert isinstance(spec, ModelSpec)
    with pytest.raises(FrozenInstanceError):
        spec.tier = "frontier"  # type: ignore[misc]
