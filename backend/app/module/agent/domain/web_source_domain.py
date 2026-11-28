"""Short ids for web pages the agent saw: ``w3`` and the ``[web:w3]`` citation."""

import re
from dataclasses import dataclass

WEB_REF_PREFIX = "w"
MAX_WEB_SOURCE_URL_CHARS = 2048
MAX_WEB_SOURCE_TITLE_CHARS = 500
_REF = re.compile(r"^w([1-9]\d{0,8})$")


@dataclass(frozen=True)
class WebSource:
    """One numbered page of a conversation."""

    ref_no: int
    url: str
    title: str | None

    @property
    def ref(self) -> str:
        """Return the short id, for example ``w3``."""
        return web_ref(self.ref_no)


def web_ref(ref_no: int) -> str:
    """Render the short id for one page number."""
    return f"{WEB_REF_PREFIX}{ref_no}"


def parse_web_ref(value: str) -> int | None:
    """Return the page number of ``w3``, or ``None`` for anything else."""
    match = _REF.match(value.strip())
    return int(match.group(1)) if match else None


def clean_title(title: str | None) -> str | None:
    """Collapse whitespace and bound a page title; empty titles become ``None``."""
    if title is None:
        return None
    collapsed = " ".join(title.split())
    return collapsed[:MAX_WEB_SOURCE_TITLE_CHARS] or None


def ephemeral_refs(urls: list[str]) -> dict[str, int]:
    """Number pages in order of first appearance when nothing is persisted.

    Used when a tool runs outside a conversation (saved questions): the numbers
    are local to that one result, which is still enough for an inline citation.
    """
    refs: dict[str, int] = {}
    for url in urls:
        if url not in refs:
            refs[url] = len(refs) + 1
    return refs
