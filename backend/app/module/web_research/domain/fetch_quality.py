"""Cheap structural checks for extracted page text.

No extractor can prove that a page was captured completely. A heading that is
immediately followed by a same-or-higher heading, or a document that ends on a
heading, is a useful warning sign: the provider may have skipped the section
body. This is deliberately a warning, not a hard failure, because some pages do
contain intentionally empty sections.
"""

import re

_HEADING = re.compile(r"^ {0,3}(#{1,6})\s+\S")


def looks_structurally_incomplete(content: str) -> bool:
    """Return whether a Markdown document has an empty-looking heading section."""
    in_fence = False
    pending_level: int | None = None
    for line in content.splitlines():
        stripped = line.lstrip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        match = _HEADING.match(line)
        if match is not None:
            level = len(match.group(1))
            if pending_level is not None and level <= pending_level:
                return True
            pending_level = level
            continue
        if line.strip():
            pending_level = None
    return pending_level is not None


__all__ = ["looks_structurally_incomplete"]
