"""HTTP contracts for the owner account and cookie sessions."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class UserSchema(BaseModel):
    model_config = ConfigDict(frozen=True)

    user_id: int
    username: str
    display_name: str | None
    bio: str | None
    created_at: datetime
    last_login_at: datetime | None


class AuthStatusSchema(BaseModel):
    model_config = ConfigDict(frozen=True)

    requires_setup: bool
    authenticated: bool
    user: UserSchema | None


class SetupSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=10, max_length=256)
    confirm_password: str = Field(min_length=10, max_length=256)


class LoginSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)


class AuthResponseSchema(BaseModel):
    model_config = ConfigDict(frozen=True)

    user: UserSchema


class UserProfileUpdateSchema(BaseModel):
    """The owner's editable display identity and self-introduction."""

    model_config = ConfigDict(extra="forbid")

    display_name: str = Field(min_length=1, max_length=80)
    bio: str | None = Field(default=None, max_length=2000)
