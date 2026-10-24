"""Small XML helpers for provider tool-result payloads.

Tool results are data, not instructions. Every dynamic value is escaped before it
enters the XML envelope, and long values are clipped before escaping so an entity
is never cut in half.
"""

from collections.abc import Mapping

TRUNCATION_MARKER = "\n[truncated]"


def xml_text(value: object) -> str:
    """Escape a value for XML element text."""
    return str(value).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def xml_attr(value: object) -> str:
    """Return a quoted XML attribute value."""
    escaped = xml_text(value).replace('"', "&quot;").replace("'", "&apos;")
    return f'"{escaped}"'


def clip(value: str, limit: int) -> str:
    """Bound a string and make truncation explicit."""
    if limit <= 0:
        return ""
    if len(value) <= limit:
        return value
    keep = max(0, limit - len(TRUNCATION_MARKER))
    return value[:keep].rstrip() + TRUNCATION_MARKER


def attributes(values: Mapping[str, object]) -> str:
    """Render a deterministic attribute string for an element."""
    return "".join(f" {key}={xml_attr(value)}" for key, value in values.items())
