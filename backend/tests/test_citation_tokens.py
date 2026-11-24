"""Citation token extraction accepts both bracket widths."""

from app.module.agent.domain.compaction_domain import _CITATION_PATTERN
from app.module.agent.service.agent_service import CITATION_PATTERN


def test_citation_pattern_matches_ascii_and_full_width_tokens() -> None:
    text = "See [memory:7], ［file:10#2］, [summary:4], and ［history:123］."

    expected = [
        "[memory:7]",
        "［file:10#2］",
        "[summary:4]",
        "［history:123］",
    ]
    assert CITATION_PATTERN.findall(text) == expected
    assert _CITATION_PATTERN.findall(text) == expected


def test_citation_pattern_ignores_unknown_kinds_and_chunked_history() -> None:
    text = "[unknown:5] ［history:123#1］"

    assert CITATION_PATTERN.findall(text) == []
    assert _CITATION_PATTERN.findall(text) == []
