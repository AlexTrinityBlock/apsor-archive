"""HTTP schemas for persistent provider-chain outage notices."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

ProviderCapability = Literal["chat", "embedding", "web_search", "web_fetch"]
ProviderOperation = Literal["chat", "text", "json", "embed", "search", "fetch"]


class ProviderAttemptSchema(BaseModel):
    """One failed provider in the chain, in attempt order."""

    model_config = ConfigDict(frozen=True)

    provider: str
    status_code: int | None
    error_code: str | None
    detail: str


class ProviderErrorNoticeReadSchema(BaseModel):
    """Safe notice state; attempts contain only sanitized provider metadata."""

    model_config = ConfigDict(frozen=True)

    id: int
    capability: ProviderCapability
    operation: ProviderOperation
    error_code: str
    status_code: int | None
    detail: str
    attempts: list[ProviderAttemptSchema]
    count: int
    first_seen_at: datetime
    last_seen_at: datetime
    resolved_at: datetime | None
    resolved_by_user_id: int | None


class ProviderErrorNoticeListSchema(BaseModel):
    """Open notices plus the unresolved count for the Accounts panel."""

    model_config = ConfigDict(frozen=True)

    notices: list[ProviderErrorNoticeReadSchema]
    open_count: int


__all__ = [
    "ProviderAttemptSchema",
    "ProviderCapability",
    "ProviderErrorNoticeListSchema",
    "ProviderErrorNoticeReadSchema",
    "ProviderOperation",
]
