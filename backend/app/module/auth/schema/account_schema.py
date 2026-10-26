"""HTTP contracts for root-only account management."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.module.auth.schema.auth_schema import UserRole


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


class AccountListSchema(BaseModel):
    """Every account, root first, then creation order."""

    model_config = ConfigDict(frozen=True)

    items: list[AccountSchema]


class AccountCreateSchema(BaseModel):
    """The root submits an initial identity; the server sets role and state."""

    model_config = ConfigDict(extra="forbid")

    username: str = Field(min_length=3, max_length=64)
    display_name: str = Field(min_length=1, max_length=80)


class AccountTemporaryPasswordSchema(BaseModel):
    """A newly generated password returned exactly once."""

    model_config = ConfigDict(frozen=True)

    user: AccountSchema
    temporary_password: str
