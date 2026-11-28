"""Readiness probes behind the public health endpoint."""

from typing import Literal

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

DatabaseStatus = Literal["ok", "error"]


async def probe_database(session: AsyncSession) -> DatabaseStatus:
    """Return ``"ok"`` when the database answers a trivial query.

    Any failure is reported as ``"error"`` so the health endpoint can answer
    503 without leaking driver details.
    """
    try:
        await session.execute(text("SELECT 1"))
    except Exception:
        return "error"
    return "ok"
