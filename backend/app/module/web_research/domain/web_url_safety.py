"""URL policy for outbound web fetches.

Tavily issues the actual HTTP request, not this service, so this is not the main
SSRF boundary; it is still defense-in-depth: it keeps the agent from asking a
third-party crawler to probe loopback, private networks, or special-use addresses,
and keeps URLs with credentials or non-http(s) schemes out of the fetch cache.

Every module-level helper is defined before ``WebUrlSafety``: if a circular
import ever appears, all the names ``WebUrlSafety`` refers to already exist by the
time it becomes available, so validate() cannot raise NameError while the import
is still incomplete.
"""

import ipaddress
from urllib.parse import SplitResult, urlsplit, urlunsplit

from app.module.web_research.exception.domain_error import WebUrlInvalidError

_MAX_URL_CHARS = 2_048
_ALLOWED_SCHEMES = frozenset({"http", "https"})
_BLOCKED_HOST_SUFFIXES = (".local", ".internal", ".localhost")


def _is_blocked_hostname(host: str) -> bool:
    """Reject loopback names and private-use DNS suffixes."""
    lowered = host.lower()
    if lowered == "localhost":
        return True
    if lowered in {"local", "internal"}:
        return True
    return lowered.endswith(_BLOCKED_HOST_SUFFIXES)


def _parse_ip_literal(host: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
    try:
        return ipaddress.ip_address(host)
    except ValueError:
        return None


def _looks_like_legacy_ipv4(host: str) -> bool:
    """Detect numeric IPv4 spellings that ``ipaddress`` rejects.

    Only hosts made up entirely of digits (or 0x hex) separated by dots in at most
    four parts are checked; a normal domain has at least one part containing a
    non-digit character, so it is never rejected by mistake.
    """
    parts = host.split(".")
    if not 1 <= len(parts) <= 4:
        return False
    for part in parts:
        value = part.lower()
        if value.startswith("0x"):
            digits = value[2:]
            if not digits or any(character not in "0123456789abcdef" for character in digits):
                return False
        elif not value.isdigit():
            return False
    return True


def _is_public_address(address: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """Return ``True`` only for globally routable unicast addresses.

    Python 3.13 reports ``is_global=True`` for multicast addresses (for example
    224.0.0.1 and ff02::1), so ``is_global`` cannot be trusted on its own; checking
    every category listed in the specification and then requiring ``is_global``
    also rejects non-public special-purpose ranges such as CGNAT 100.64/10.
    An IPv4-mapped IPv6 address (::ffff:127.0.0.1) must have the embedded IPv4
    address extracted first, otherwise it is treated as an ordinary IPv6 address
    and slips through.
    """
    mapped = getattr(address, "ipv4_mapped", None)
    if mapped is not None:
        return _is_public_address(mapped)
    if (
        address.is_private
        or address.is_loopback
        or address.is_link_local
        or address.is_multicast
        or address.is_reserved
        or address.is_unspecified
    ):
        return False
    return address.is_global


class WebUrlSafety:
    """Pure, stateless URL validation and normalization."""

    @staticmethod
    def validate(url: str) -> str:
        """Return a normalized URL or raise :class:`WebUrlInvalidError`.

        Normalization is a prerequisite for cache correctness: different spellings
        of the same resource (case, default port, empty path, fragment) must
        converge on one string so the fetch cache key stays stable; a fragment is
        never sent to the server, so it is always removed.
        """
        raw = url.strip()
        if not raw or len(raw) > _MAX_URL_CHARS:
            raise WebUrlInvalidError("URL must contain 1 to 2048 characters.")
        # Control characters and whitespace can make different parsers derive a
        # different host (browser vs urllib), so they are rejected outright to keep
        # one string from being read differently by the two layers.
        if any(character.isspace() or ord(character) < 0x20 for character in raw):
            raise WebUrlInvalidError("URL must not contain whitespace or control characters.")

        try:
            parts = urlsplit(raw)
        except ValueError as exc:
            raise WebUrlInvalidError("URL could not be parsed.") from exc

        scheme = parts.scheme.lower()
        if scheme not in _ALLOWED_SCHEMES:
            raise WebUrlInvalidError("Only http and https URLs are allowed.")
        # A username/password would show up in provider logs and error messages and
        # serves no purpose for fetching.
        if parts.username is not None or parts.password is not None:
            raise WebUrlInvalidError("URLs must not contain credentials.")

        host = parts.hostname
        if not host:
            raise WebUrlInvalidError("URL must include a hostname.")
        # urlsplit already lowercases the hostname; a trailing DNS dot (example.com.)
        # and the dotless spelling are equivalent, so it is stripped before the
        # reserved-domain check to block bypasses such as `localhost.`.
        normalized_host = host.rstrip(".")
        if not normalized_host:
            raise WebUrlInvalidError("URL must include a hostname.")
        if _is_blocked_hostname(normalized_host):
            raise WebUrlInvalidError("URL host is not reachable from the public internet.")
        address = _parse_ip_literal(normalized_host)
        if address is not None and not _is_public_address(address):
            raise WebUrlInvalidError("URL host is a private or special-use address.")
        # Browsers and inet_aton accept legacy IPv4 spellings such as 127.1,
        # 0x7f000001, or 2130706433 that ipaddress rejects; letting them through
        # would still let Tavily resolve to loopback.
        if address is None and _looks_like_legacy_ipv4(normalized_host):
            raise WebUrlInvalidError("URL host is a private or special-use address.")

        try:
            port = parts.port
        except ValueError as exc:
            raise WebUrlInvalidError("URL port is invalid.") from exc
        # Omit the default port so `https://example.com` and `https://example.com:443`
        # produce the same cache key.
        if port is not None and port == (80 if scheme == "http" else 443):
            port = None

        netloc = f"[{normalized_host}]" if ":" in normalized_host else normalized_host
        if port is not None:
            netloc = f"{netloc}:{port}"
        return urlunsplit(
            SplitResult(
                scheme=scheme,
                netloc=netloc,
                path=parts.path or "/",
                query=parts.query,
                fragment="",
            )
        )
