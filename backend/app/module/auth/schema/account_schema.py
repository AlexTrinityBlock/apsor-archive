"""HTTP contracts for root-only account management."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.module.auth.schema.auth_schema import UserRole

QuotaCategorySchema = Literal["chat", "embedding", "web_search", "web_fetch"]


class AccountUsageSchema(BaseModel):
    """Rolled-up agent usage for one account."""

    model_config = ConfigDict(frozen=True)

    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    cached_tokens: int
    api_calls: int
    turns: int
    last_activity_at: datetime | None


class AccountQuotaSchema(BaseModel):
    """One allowance category as the root console projects it.

    ``used`` is the current cycle (``lifetime - used_before_reset``), while
    ``lifetime`` stays the monotonic counter. ``remaining`` is null only when
    the grant is unlimited.
    """

    model_config = ConfigDict(frozen=True)

    category: QuotaCategorySchema
    enabled: bool
    granted: int | None
    used: int
    used_before_reset: int
    lifetime: int
    remaining: int | None


class AccountSchema(BaseModel):
    """One account row without any credential material."""

    model_config = ConfigDict(frozen=True)

    user_id: int
    username: str
    display_name: str | None
    role: UserRole
    is_active: bool
    must_change_password: bool
    created_at: datetime
    last_login_at: datetime | None
    usage: AccountUsageSchema
    quotas: list[AccountQuotaSchema]


class AccountListSchema(BaseModel):
    """Every account, root first, then creation order."""

    model_config = ConfigDict(frozen=True)

    items: list[AccountSchema]


class AccountCreateSchema(BaseModel):
    """The root submits an initial identity; the server sets role and state."""

    model_config = ConfigDict(extra="forbid")

    username: str = Field(min_length=3, max_length=64)
    display_name: str = Field(min_length=1, max_length=80)


class AccountQuotaUpdateSchema(BaseModel):
    """Replace one category's enabled switch and finite grant.

    Both fields are required. ``granted`` is null for unlimited and must be a
    non-negative integer otherwise; the service validates the bound so an
    invalid mutation returns the stable ``invalid_usage_quota`` domain error.
    """

    model_config = ConfigDict(extra="forbid")

    enabled: bool
    granted: int | None


class AccountQuotaTopUpSchema(BaseModel):
    """Increase a finite grant atomically.

    ``amount`` must be positive and is bounded by the service; topping up an
    unlimited grant is rejected because there is no finite number to increase.
    """

    model_config = ConfigDict(extra="forbid")

    amount: int


class AccountQuotaResetSchema(BaseModel):
    """Start a new cycle for one category.

    ``granted`` is required and nullable: null keeps the category unlimited,
    while an integer sets the new finite allowance. Send the current grant to
    keep it unchanged. The prior cumulative usage is preserved in
    ``used_before_reset``; a reset is not a history wipe.
    """

    model_config = ConfigDict(extra="forbid")

    granted: int | None


class AccountTemporaryPasswordSchema(BaseModel):
    """A newly generated password returned exactly once."""

    model_config = ConfigDict(frozen=True)

    user: AccountSchema
    temporary_password: str
