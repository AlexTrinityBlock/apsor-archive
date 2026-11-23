"""Deterministic compaction template, budgets, and runtime config bounds.

These are pure domain tests: no database, no provider fake, and no clock. The
compaction builder must be reproducible byte for byte, because the same input
feeds both the stored transcript projection and the overflow ladder.
"""

from typing import Any

import httpx
import pytest

from app.module.agent.domain.agent_config_domain import AgentRuntimeConfig
from app.module.agent.domain.agent_domain import (
    COMPACTION_MAX_OUTPUT_TOKENS,
    DEFAULT_COMPACTION_PROMPT,
    KIND_ASSISTANT,
    KIND_COMPACTION,
    KIND_PAGE_CONTEXT,
    KIND_TOOL_RESULT,
    KIND_USER,
    EntryDraft,
    ProviderContext,
    TranscriptEntry,
)
from app.module.agent.domain.compaction_domain import (
    CHARS_PER_ESTIMATED_TOKEN,
    MAX_COMPACTION_LAST_USER_CHARS,
    MAX_COMPACTION_SUMMARY_CHARS,
    MAX_SUMMARY_ITEM_CHARS,
    MAX_SUMMARY_ITEMS,
    build_compaction_draft,
    estimate_context_tokens,
    estimate_provider_context_tokens,
    render_compaction_prompt,
)
from app.module.agent.domain.xml_domain import TRUNCATION_MARKER


def _entry(
    entry_id: int,
    kind: str,
    *,
    text: str = "",
    data: dict[str, Any] | None = None,
) -> TranscriptEntry:
    """Build one minimal transcript entry for a deterministic summary."""
    messages: tuple[dict[str, Any], ...] = ()
    if text:
        role = "user" if kind == KIND_USER else "assistant"
        messages = ({"role": role, "content": text},)
    return TranscriptEntry(id=entry_id, kind=kind, messages=messages, data=data)


def _representative_transcript() -> list[TranscriptEntry]:
    """Return a transcript that exercises every summary line type."""
    return [
        _entry(1, KIND_USER, text="First question about the wrench."),
        _entry(2, KIND_ASSISTANT, text="The wrench is a hand tool [file:3#1]."),
        _entry(3, KIND_USER, text="Second question about the timeline."),
        TranscriptEntry(
            id=4,
            kind=KIND_TOOL_RESULT,
            data={"tool": "read_file", "status": "ok"},
        ),
        TranscriptEntry(
            id=5,
            kind=KIND_PAGE_CONTEXT,
            data={"page_key": "wrench", "path": "/wrench.md"},
        ),
        _entry(6, KIND_ASSISTANT, text="The timeline remains sparse."),
    ]


def _counting_transcript(count: int = 12) -> list[TranscriptEntry]:
    """Alternate user and assistant entries with stable, searchable text."""
    entries: list[TranscriptEntry] = []
    for index in range(1, count + 1):
        if index % 2:
            entries.append(
                _entry(
                    index,
                    KIND_USER,
                    text=f"Question {index:02d} " + "x" * 40,
                )
            )
        else:
            entries.append(
                _entry(
                    index,
                    KIND_ASSISTANT,
                    text=f"Answer {index:02d} " + "y" * 40,
                )
            )
    return entries


def _provider_context() -> ProviderContext:
    """Build one provider request for the token-estimate ratio tests."""
    return ProviderContext(
        system_message={"role": "system", "content": "You are Apsor Archive."},
        tools=[],
        messages=[{"role": "user", "content": "x" * 300}],
        source_entry_ids=[1],
        cache_prefix_hash="hash",
    )


# Legacy golden output from the pre-template compactor. The bounded path must
# never change this: existing threshold compaction stores exactly these bytes.
_LEGACY_SUMMARY = (
    "User: First question about the wrench.\n"
    "Assistant: The wrench is a hand tool [file:3#1]. citations=[file:3#1]\n"
    "User: Second question about the timeline.\n"
    "Tool read_file: ok\n"
    "Page context: wrench\n"
    "Assistant: The timeline remains sparse."
)
_LEGACY_CONTENT = (
    "<compaction>"
    "<last_user_input>Second question about the timeline.</last_user_input>"
    f"<summary>{_LEGACY_SUMMARY}</summary>"
    "</compaction>"
)


def test_agent_runtime_config_defaults_include_compaction_fields() -> None:
    """The new runtime fields share the defaults the migration seeds."""
    config = AgentRuntimeConfig()

    assert config.model_escalation_enabled is True
    assert config.compaction_prompt == DEFAULT_COMPACTION_PROMPT
    assert config.compaction_max_output_tokens == COMPACTION_MAX_OUTPUT_TOKENS
    assert config.compaction_max_output_tokens == 2_600
    assert config.agent_max_output_tokens == 64_000


@pytest.mark.parametrize(
    ("prompt", "match"),
    [
        ("", "between 1 and 20000 characters"),
        ("x" * 20_001, "between 1 and 20000 characters"),
        ("The summary is bounded.", "max_output_tokens"),
        ("The summary is bounded by {unknown_placeholder}.", "unknown_placeholder"),
        ("The summary is bounded by {max_output_tokens", "unmatched brace"),
        ("The summary is bounded by max_output_tokens}.", "unmatched brace"),
        ("The summary is bounded by {max_output_tokens!r}.", "conversions"),
        ("The summary is bounded by {max_output_tokens:>8}.", "format specifications"),
    ],
)
def test_agent_runtime_config_rejects_invalid_compaction_prompts(
    prompt: str,
    match: str,
) -> None:
    """A missing bound, an unknown placeholder, or a stray brace is rejected."""
    with pytest.raises(ValueError, match=match):
        AgentRuntimeConfig(compaction_prompt=prompt)


def test_agent_runtime_config_accepts_doubled_literal_braces() -> None:
    """A literal brace is allowed when it is escaped the ``str.format`` way."""
    config = AgentRuntimeConfig(
        compaction_prompt="Literal {{braces}} plus {max_output_tokens} tokens."
    )

    assert "{{braces}}" in config.compaction_prompt


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("compaction_max_output_tokens", 256),
        ("compaction_max_output_tokens", 16_384),
        ("agent_max_output_tokens", 256),
        ("agent_max_output_tokens", 131_072),
    ],
)
def test_agent_runtime_config_accepts_cap_boundaries(field: str, value: int) -> None:
    """The database CHECK bounds are inclusive."""
    config = AgentRuntimeConfig(**{field: value})

    assert getattr(config, field) == value


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("compaction_max_output_tokens", 255),
        ("compaction_max_output_tokens", 16_385),
        ("compaction_max_output_tokens", 32_000),
        ("agent_max_output_tokens", 255),
        ("agent_max_output_tokens", 131_073),
    ],
)
def test_agent_runtime_config_rejects_out_of_range_caps(field: str, value: int) -> None:
    """The compaction cap must not accept the old 32,000-token attempt."""
    with pytest.raises(ValueError, match=field):
        AgentRuntimeConfig(**{field: value})


def test_render_compaction_prompt_states_token_and_character_bounds() -> None:
    """The rendered instruction always states both sides of the output cap."""
    rendered = render_compaction_prompt(
        DEFAULT_COMPACTION_PROMPT,
        max_output_tokens=2_600,
        chars_per_token=2.3,
    )

    assert "2600 tokens" in rendered
    assert "5980 characters" in rendered
    assert f"at most {MAX_SUMMARY_ITEMS} items" in rendered
    assert f"at most {MAX_SUMMARY_ITEM_CHARS} characters" in rendered
    assert f"at most {MAX_COMPACTION_LAST_USER_CHARS} characters" in rendered


def test_render_compaction_prompt_uses_the_catalog_ratio() -> None:
    """A DeepSeek-style ratio changes the character sentence, not the token one."""
    rendered = render_compaction_prompt(
        DEFAULT_COMPACTION_PROMPT,
        max_output_tokens=2_600,
        chars_per_token=3.0,
    )

    assert "2600 tokens" in rendered
    assert "7800 characters" in rendered


def test_render_compaction_prompt_accepts_a_custom_placeholder_set() -> None:
    """Any subset of the known placeholders renders, including escaped braces."""
    rendered = render_compaction_prompt(
        "Bound {max_output_tokens} tokens ({max_output_chars} chars); "
        "items {max_items}; line {max_line_chars}; carry {max_last_user_chars}. "
        "Literal {{brace}}.",
        max_output_tokens=512,
        chars_per_token=2.0,
        max_items=7,
        max_line_chars=90,
        max_last_user_chars=120,
    )

    assert rendered == (
        "Bound 512 tokens (1024 chars); items 7; line 90; carry 120. "
        "Literal {brace}."
    )


@pytest.mark.parametrize(
    ("template", "match"),
    [
        ("No output bound.", "max_output_tokens"),
        ("Bound by {unknown_placeholder}.", "unknown placeholder"),
        ("Bound by {max_output_tokens", "unmatched brace"),
        ("Bound by max_output_tokens}.", "unmatched brace"),
        ("Bound by {max_output_tokens!r}.", "conversions"),
        ("Bound by {max_output_tokens:>8}.", "format specifications"),
    ],
)
def test_render_compaction_prompt_rejects_invalid_templates(
    template: str,
    match: str,
) -> None:
    """The renderer rejects the same bad templates the settings panel rejects."""
    with pytest.raises(ValueError, match=match):
        render_compaction_prompt(template, max_output_tokens=100)


def test_render_compaction_prompt_rejects_unknown_context_values() -> None:
    """A misspelled context name fails instead of rendering stale defaults."""
    with pytest.raises(ValueError, match="unknown context"):
        render_compaction_prompt(
            "{max_output_tokens}",
            max_output_tokens=100,
            max_item=10,
        )


@pytest.mark.parametrize("value", [0, -1, True])
def test_render_compaction_prompt_rejects_invalid_token_bounds(value: int) -> None:
    """A rendered instruction always needs a positive token bound."""
    with pytest.raises(ValueError, match="max_output_tokens"):
        render_compaction_prompt("{max_output_tokens}", max_output_tokens=value)


def test_build_compaction_draft_without_target_tokens_preserves_legacy_output() -> None:
    """Omitting the budget keeps the exact pre-template output and metadata."""
    draft = build_compaction_draft(
        _representative_transcript(),
        reason="manual",
        auto=False,
    )

    assert draft == EntryDraft(
        kind=KIND_COMPACTION,
        messages=[{"role": "user", "content": _LEGACY_CONTENT}],
        data={
            "reason": "manual",
            "summary_chars": len(_LEGACY_SUMMARY),
            "last_user_entry_id": 3,
            "source_entry_ids": [1, 2, 3, 4, 5, 6],
            "auto": False,
        },
    )


def test_build_compaction_draft_explicit_none_is_the_legacy_path() -> None:
    """An explicit ``target_tokens=None`` is not a separate code path."""
    entries = _representative_transcript()

    implicit = build_compaction_draft(entries, reason="manual", auto=False)
    explicit = build_compaction_draft(
        entries,
        reason="manual",
        auto=False,
        target_tokens=None,
    )

    assert implicit == explicit


def test_build_compaction_draft_target_tokens_keeps_newest_whole_items() -> None:
    """The 60% ladder budget keeps a newest suffix and never splits an item."""
    entries = _counting_transcript()
    target_tokens = 100
    chars_per_token = 3.0
    budget_chars = target_tokens * chars_per_token

    draft = build_compaction_draft(
        entries,
        reason="forced_context_budget",
        auto=True,
        target_tokens=target_tokens,
        chars_per_token=chars_per_token,
    )
    content = draft.messages[0]["content"]
    source_ids = draft.data["source_entry_ids"]

    assert len(content) <= budget_chars
    assert draft.data["summary_chars"] <= min(
        MAX_COMPACTION_SUMMARY_CHARS,
        budget_chars,
    )
    assert source_ids
    assert source_ids[-1] == 12
    assert source_ids == list(range(source_ids[0], 13))
    assert source_ids[0] > 1
    assert "Answer 12" in content
    assert "Question 01" not in content
    assert "earlier entries omitted" in content
    assert TRUNCATION_MARKER not in content


def test_build_compaction_draft_target_tokens_honours_the_summary_cap() -> None:
    """The legacy character cap still wins when it is smaller than the budget."""
    draft = build_compaction_draft(
        _counting_transcript(),
        reason="forced_context_budget",
        auto=True,
        max_summary_chars=100,
        max_last_user_chars=80,
        target_tokens=200,
    )
    content = draft.messages[0]["content"]

    assert draft.data["summary_chars"] <= 100
    assert len(content) <= 200 * CHARS_PER_ESTIMATED_TOKEN
    assert "earlier entries omitted" in content
    assert TRUNCATION_MARKER not in content


def test_build_compaction_draft_target_tokens_caps_the_carry_line() -> None:
    """A long last request is clipped so the entry still fits its budget."""
    entries = [
        _entry(1, KIND_USER, text="Q " + "x" * 500),
        _entry(2, KIND_ASSISTANT, text="A " + "y" * 500),
        _entry(3, KIND_USER, text="LAST " + "z" * 1_000),
    ]
    budget_chars = 100 * CHARS_PER_ESTIMATED_TOKEN

    draft = build_compaction_draft(
        entries,
        reason="forced_context_budget",
        auto=True,
        target_tokens=100,
    )
    content = draft.messages[0]["content"]
    carried = content.split("<last_user_input>", 1)[1].split(
        "</last_user_input>",
        1,
    )[0]

    assert len(content) <= budget_chars
    assert len(carried) <= budget_chars
    assert carried.startswith("LAST")
    assert carried.endswith(TRUNCATION_MARKER)


def test_build_compaction_draft_target_tokens_is_deterministic() -> None:
    """The same transcript and budget always produce the same entry."""
    entries = _counting_transcript()

    first = build_compaction_draft(
        entries,
        reason="forced_context_budget",
        auto=True,
        target_tokens=100,
    )
    second = build_compaction_draft(
        list(entries),
        reason="forced_context_budget",
        auto=True,
        target_tokens=100,
    )

    assert first == second


@pytest.mark.parametrize("target", [0, -1, True])
def test_build_compaction_draft_rejects_invalid_target_tokens(target: int) -> None:
    """A target budget must be a positive integer."""
    with pytest.raises(ValueError, match="target_tokens"):
        build_compaction_draft(
            _representative_transcript(),
            reason="forced_context_budget",
            auto=True,
            target_tokens=target,
        )


def test_build_compaction_draft_never_calls_a_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Compaction has no provider seam, so every HTTP send is forbidden."""
    def _forbidden(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("compaction must not call a provider")

    async def _forbidden_async(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("compaction must not call a provider")

    monkeypatch.setattr(httpx.Client, "send", _forbidden)
    monkeypatch.setattr(httpx.AsyncClient, "send", _forbidden_async)

    implicit = build_compaction_draft(
        _representative_transcript(),
        reason="manual",
        auto=False,
    )
    bounded = build_compaction_draft(
        _counting_transcript(),
        reason="forced_context_budget",
        auto=True,
        target_tokens=100,
    )

    assert implicit.messages
    assert bounded.messages


def test_estimate_provider_context_tokens_uses_the_given_ratio() -> None:
    """A tighter ratio produces a larger estimate without a provider call."""
    context = _provider_context()

    default = estimate_provider_context_tokens(context)
    narrow = estimate_provider_context_tokens(context, chars_per_token=1.5)
    wide = estimate_provider_context_tokens(context, chars_per_token=6.0)

    assert narrow > default > wide
    assert default == estimate_provider_context_tokens(
        context,
        chars_per_token=float(CHARS_PER_ESTIMATED_TOKEN),
    )


def test_estimate_context_tokens_threads_the_ratio() -> None:
    """The entry estimate passes the catalog ratio to the context estimate."""
    entries = [_entry(1, KIND_USER, text="z" * 300)]

    default = estimate_context_tokens(entries)
    narrow = estimate_context_tokens(entries, chars_per_token=1.5)
    wide = estimate_context_tokens(entries, chars_per_token=6.0)

    assert narrow > default > wide


def test_estimate_context_tokens_keeps_the_usage_anchor() -> None:
    """A real provider usage figure still wins over a tiny char estimate."""
    entries = [
        _entry(1, KIND_USER, text="short"),
        TranscriptEntry(
            id=2,
            kind=KIND_ASSISTANT,
            messages=({"role": "assistant", "content": "ok"},),
            data={"usage": {"prompt_tokens": 9_000, "completion_tokens": 500}},
        ),
    ]

    assert estimate_context_tokens(entries, chars_per_token=1_000.0) == 9_500


@pytest.mark.parametrize("ratio", [0, -1.0])
def test_token_estimates_reject_non_positive_ratios(ratio: float) -> None:
    """A non-positive ratio would divide by zero or invert the estimate."""
    context = _provider_context()

    with pytest.raises(ValueError, match="chars_per_token"):
        estimate_provider_context_tokens(context, chars_per_token=ratio)
    with pytest.raises(ValueError, match="chars_per_token"):
        estimate_context_tokens(
            [_entry(1, KIND_USER, text="x")],
            chars_per_token=ratio,
        )
