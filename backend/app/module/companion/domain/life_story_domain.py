"""Pure rules for generated life stories.

A life story is written by the account's own model when the librarians'
world opens an illusory door onto a corner of the account's life. This module
holds everything about it that needs no I/O: when one is due, how prompt
templates are rendered, how the model's output is parsed and judged, and the
stable codes a job ends with.
"""

import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta

# Placeholders every life-story prompt may use. Rendering replaces only these
# names, so braces inside memories or canon never act as format fields.
LIFE_STORY_PLACEHOLDERS: tuple[str, ...] = (
    "companion_name",
    "persona",
    "canon",
    "memories",
    "language",
    "max_chars",
)
SYSTEM_REQUIRED_PLACEHOLDERS: tuple[str, ...] = ("companion_name", "persona", "language")
USER_REQUIRED_PLACEHOLDERS: tuple[str, ...] = ("canon", "memories", "language", "max_chars")

# Hard ceiling from the ``companion_generated_story`` CHECK constraints.
STORY_TEXT_HARD_MAX = 4000
STORY_TITLE_MAX = 120
STORY_MIN_CHARS = 80
LIFE_STORY_WINDOW = timedelta(days=30)
LEASE_SECONDS = 600
BACKOFF_BASE_SECONDS = 60
BACKOFF_MAX_SECONDS = 3600

LANGUAGE_NAMES: Mapping[str, str] = {
    "en": "English",
    "zh-TW": "Traditional Chinese as written in Taiwan",
    "zh-CN": "Simplified Chinese as written in mainland China",
}

# Terminal and skip codes stored on ``companion_story_job``. They are stable
# machine-readable values; logs carry the code and ids, never content.
SKIP_DISABLED = "disabled"
SKIP_MODEL_NOT_ASSIGNED = "model_not_assigned"
SKIP_QUOTA = "quota"
SKIP_NO_MATERIAL = "no_material"
SKIP_COMPANION_GONE = "companion_not_found"
FAIL_PROVIDER_UNAVAILABLE = "provider_unavailable"
FAIL_PROVIDER_REJECTED = "provider_rejected"
FAIL_TEMPLATE_INVALID = "template_invalid"
FAIL_LEASE_EXPIRED = "lease_expired"
FAIL_INTERNAL = "internal_error"
REJECT_EMPTY = "story_empty"
REJECT_TOO_SHORT = "story_too_short"
REJECT_BANNED_ADDRESS = "story_banned_address"

ACTIVE_JOB_STATUSES: tuple[str, ...] = ("queued", "running", "cancel_requested")

_CITATION_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\[(?:file|memory|summary|history|web|lore)\s*:[^\]]*\]", re.IGNORECASE),
    re.compile(r"</?cite[^>]*>", re.IGNORECASE),
    re.compile(r"</?librarian_memor(?:y|ies)[^>]*>", re.IGNORECASE),
)
_FENCE = re.compile(r"^```[a-zA-Z]*\s*$")
_TITLE_PREFIX = re.compile(r"^(?:#+\s*|title\s*[:：]\s*|標題\s*[:：]\s*|标题\s*[:：]\s*)", re.I)
_QUOTES = "\"'“”‘’「」『』《》"
_SENTENCE_END = re.compile(r"[.!?。！？…」』”](?=\s|$)")
_LATIN = re.compile(r"^[a-z][a-z ]*$")


class LifeStoryTemplateError(ValueError):
    """A prompt template is missing a placeholder it needs."""

    def __init__(self, missing: Sequence[str]) -> None:
        self.missing = tuple(missing)
        super().__init__("template is missing placeholders: " + ", ".join(self.missing))


class LifeStoryRejectedError(ValueError):
    """The model's output cannot be kept; ``code`` is a stable reject code."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class LifeStoryGenerationError(Exception):
    """A model call that produced no story, classified for the job.

    ``skip`` errors end the job as ``skipped`` (no model, no allowance);
    ``retryable`` errors requeue it with backoff until attempts run out; the
    rest fail it. The composition root maps provider errors onto these.
    """

    def __init__(self, code: str, *, retryable: bool = False, skip: bool = False) -> None:
        self.code = code
        self.retryable = retryable
        self.skip = skip
        super().__init__(code)


@dataclass(frozen=True)
class ParsedStory:
    """A judged story ready to store."""

    title: str
    text: str


@dataclass(frozen=True)
class SourceRefs:
    """Which archive items a story drew on: ids and counts only, never content."""

    memory_ids: tuple[int, ...] = ()
    file_ids: tuple[int, ...] = ()

    def as_json(self) -> dict[str, object]:
        """Return the JSON stored in ``companion_generated_story.source_refs``."""
        return {
            "memory_ids": list(self.memory_ids),
            "file_ids": list(self.file_ids),
            "memory_count": len(self.memory_ids),
            "file_count": len(self.file_ids),
        }


def language_name(locale: str) -> str:
    """Return the writing language for ``locale`` (English when unknown)."""
    return LANGUAGE_NAMES.get(locale, LANGUAGE_NAMES["en"])


def missing_placeholders(template: str, required: Iterable[str]) -> list[str]:
    """Return the required placeholders absent from ``template``."""
    return [name for name in required if "{" + name + "}" not in template]


def render_prompt(
    template: str,
    values: Mapping[str, object],
    required: Sequence[str] = (),
) -> str:
    """Fill the known ``{placeholders}`` of ``template``.

    Only names in :data:`LIFE_STORY_PLACEHOLDERS` are replaced, one at a time,
    so text inside a value (a memory with braces, say) is never reinterpreted.
    Raises :class:`LifeStoryTemplateError` when a required placeholder is
    missing, so an admin-edited template that drops one fails loudly.
    """
    missing = missing_placeholders(template, required)
    if missing or not template.strip():
        raise LifeStoryTemplateError(missing or list(required))
    rendered = template
    for name in LIFE_STORY_PLACEHOLDERS:
        token = "{" + name + "}"
        if token in rendered:
            rendered = rendered.replace(token, str(values.get(name, "")))
    return rendered


def strip_citations(text: str) -> str:
    """Remove archive citation markup a model may have copied into a story."""
    cleaned = text
    for pattern in _CITATION_PATTERNS:
        cleaned = pattern.sub("", cleaned)
    return re.sub(r"[ \t]{2,}", " ", cleaned)


def _contains_term(text: str, term: str) -> bool:
    lowered = text.lower()
    needle = term.lower().strip()
    if not needle:
        return False
    if _LATIN.match(needle):
        return re.search(r"(?<![a-z])" + re.escape(needle) + r"(?![a-z])", lowered) is not None
    return needle in lowered


def find_banned_term(text: str, banned_terms: Iterable[str]) -> str | None:
    """Return the first banned address term in ``text`` (whole words for Latin)."""
    return next((term for term in banned_terms if _contains_term(text, term)), None)


def _clip_at_sentence(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    window = text[:max_chars]
    ends = list(_SENTENCE_END.finditer(window))
    if ends and ends[-1].end() >= max_chars // 2:
        return window[: ends[-1].end()].rstrip()
    return window.rstrip() + "…"


def parse_story(output: str, *, max_chars: int, banned_terms: Iterable[str]) -> ParsedStory:
    """Split a title line from the body, clean it, and judge it.

    The first non-empty line is the title; the rest is the story. Citation
    markup and code fences are removed. A story with a banned form of address
    (Keeper, master, 館主…) is rejected; one that runs long is clipped at a
    sentence end within ``max_chars``.
    """
    lines = [line for line in output.replace("\r\n", "\n").split("\n") if not _FENCE.match(line)]
    while lines and not lines[0].strip():
        lines.pop(0)
    if not lines:
        raise LifeStoryRejectedError(REJECT_EMPTY)
    title = lines[0].strip()
    while True:
        stripped = _TITLE_PREFIX.sub("", title).strip()
        if stripped == title:
            break
        title = stripped
    title = title.strip(_QUOTES + " *_").strip()
    body = strip_citations("\n".join(lines[1:])).strip()
    if not body:
        # A single paragraph without a title line: keep it as the body.
        body = strip_citations(lines[0]).strip()
        title = ""
    body = re.sub(r"\n{3,}", "\n\n", body)
    if len(body) < STORY_MIN_CHARS:
        raise LifeStoryRejectedError(REJECT_TOO_SHORT)
    limit = max(STORY_MIN_CHARS, min(max_chars, STORY_TEXT_HARD_MAX))
    body = _clip_at_sentence(body, limit)
    if not title:
        title = body.split("\n", 1)[0][:40].rstrip(" ,.;:，。；：") or "…"
    title = title[:STORY_TITLE_MAX]
    if find_banned_term(f"{title}\n{body}", banned_terms) is not None:
        raise LifeStoryRejectedError(REJECT_BANNED_ADDRESS)
    return ParsedStory(title=title, text=body)


def life_story_due(
    *,
    enabled: bool,
    conversations: int,
    last_life_story_conversations: int,
    every_conversations: int,
    stories_last_30d: int,
    max_per_30d: int,
    has_active_job: bool,
) -> bool:
    """Return whether a cadence life story should be queued now."""
    if not enabled or has_active_job:
        return False
    if conversations - last_life_story_conversations < max(1, every_conversations):
        return False
    return stories_last_30d < max(0, max_per_30d)


def cadence_trigger_key(companion_ref: str, conversations: int) -> str:
    """Return the idempotency key of the cadence job at ``conversations``."""
    return f"cadence:{companion_ref}:{conversations}"[:128]


def generated_fragment_key(story_id: int) -> str:
    """Return the lore key of a generated story (``g-<id>``)."""
    return f"g-{story_id}"


def pending_fragment_key(job_id: int) -> str:
    """Return the temporary key a story row carries until its id is known."""
    return f"g-pending-{job_id}"


def retry_delay(attempts: int) -> timedelta:
    """Return the backoff before attempt ``attempts + 1`` (exponential, capped)."""
    seconds = BACKOFF_BASE_SECONDS * 2 ** max(0, attempts - 1)
    return timedelta(seconds=min(BACKOFF_MAX_SECONDS, seconds))


def window_start(now: datetime) -> datetime:
    """Return the start of the rolling 30-day cap window."""
    return now - LIFE_STORY_WINDOW


def clip_text(text: str, max_chars: int) -> str:
    """Clip ``text`` to ``max_chars`` characters with an ellipsis."""
    cleaned = " ".join(text.split())
    if len(cleaned) <= max_chars:
        return cleaned
    return cleaned[: max(0, max_chars - 1)].rstrip() + "…"


__all__ = [
    "ACTIVE_JOB_STATUSES",
    "FAIL_INTERNAL",
    "FAIL_LEASE_EXPIRED",
    "FAIL_PROVIDER_REJECTED",
    "FAIL_PROVIDER_UNAVAILABLE",
    "FAIL_TEMPLATE_INVALID",
    "LEASE_SECONDS",
    "LIFE_STORY_PLACEHOLDERS",
    "REJECT_BANNED_ADDRESS",
    "REJECT_EMPTY",
    "REJECT_TOO_SHORT",
    "SKIP_COMPANION_GONE",
    "SKIP_DISABLED",
    "SKIP_MODEL_NOT_ASSIGNED",
    "SKIP_NO_MATERIAL",
    "SKIP_QUOTA",
    "STORY_MIN_CHARS",
    "STORY_TEXT_HARD_MAX",
    "SYSTEM_REQUIRED_PLACEHOLDERS",
    "USER_REQUIRED_PLACEHOLDERS",
    "LifeStoryGenerationError",
    "LifeStoryRejectedError",
    "LifeStoryTemplateError",
    "ParsedStory",
    "SourceRefs",
    "cadence_trigger_key",
    "clip_text",
    "find_banned_term",
    "generated_fragment_key",
    "language_name",
    "life_story_due",
    "missing_placeholders",
    "parse_story",
    "pending_fragment_key",
    "render_prompt",
    "retry_delay",
    "strip_citations",
    "window_start",
]
