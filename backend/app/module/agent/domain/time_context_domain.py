"""Trusted current-time metadata for provider turns.

The frozen system prompt cannot carry a clock: it is created once per
conversation. Instead the user entry stores one small ``<current_time>`` block
that is appended after the message text when the message is created. The server
supplies authoritative UTC; the browser supplies its IANA timezone (or a fixed
offset as a fallback). Historical blocks are immutable, so retries never rewrite
the provider prefix.
"""

from datetime import UTC, datetime, timedelta, timezone, tzinfo
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


def _offset_label(offset: timedelta) -> str:
    total_minutes = int(offset.total_seconds() // 60)
    sign = "+" if total_minutes >= 0 else "-"
    hours, minutes = divmod(abs(total_minutes), 60)
    return f"UTC{sign}{hours:02d}:{minutes:02d}"


def _resolve_timezone(
    client_timezone: str | None,
    client_utc_offset_minutes: int | None,
    server_timezone: str,
) -> tuple[tzinfo, str, str]:
    """Return (timezone, label, source), preferring the browser zone."""
    if client_timezone:
        try:
            return ZoneInfo(client_timezone), client_timezone, "browser"
        except (ZoneInfoNotFoundError, ValueError):
            pass
    if client_utc_offset_minutes is not None:
        offset = timedelta(minutes=client_utc_offset_minutes)
        label = _offset_label(offset)
        return timezone(offset), label, "browser-offset"
    try:
        return ZoneInfo(server_timezone), server_timezone, "server"
    except (ZoneInfoNotFoundError, ValueError):
        return UTC, "UTC", "server"


def current_time_block(
    *,
    now: datetime,
    client_timezone: str | None,
    client_utc_offset_minutes: int | None,
    server_timezone: str,
) -> str:
    """Render one trusted clock block for the provider."""
    resolved, label, source = _resolve_timezone(
        client_timezone,
        client_utc_offset_minutes,
        server_timezone,
    )
    utc_now = now.astimezone(UTC)
    local_now = utc_now.astimezone(resolved)
    offset = local_now.utcoffset() or timedelta(0)
    return (
        "<current_time>\n"
        f"utc: {utc_now.isoformat(timespec='seconds').replace('+00:00', 'Z')}\n"
        f"timezone: {label} ({_offset_label(offset)})\n"
        f"timezone_source: {source}\n"
        f"local: {local_now.isoformat(timespec='seconds')}\n"
        "</current_time>"
    )
