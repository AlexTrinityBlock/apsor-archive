"""HTTP contracts for accounts and cookie sessions."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

type UserRole = Literal["root", "user"]


class UserSchema(BaseModel):
    model_config = ConfigDict(frozen=True)

    user_id: int
    username: str
    display_name: str | None
    role: UserRole
    is_active: bool
    must_change_password: bool
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


class ChangePasswordSchema(BaseModel):
    """Self-service password change, also used while a change is forced."""

    model_config = ConfigDict(extra="forbid")

    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=10, max_length=256)
    confirm_password: str = Field(min_length=10, max_length=256)


class AuthResponseSchema(BaseModel):
    model_config = ConfigDict(frozen=True)

    user: UserSchema


class UserProfileCardSchema(BaseModel):
    """One ordered profile card returned to the browser."""

    model_config = ConfigDict(frozen=True, from_attributes=True)

    card_id: int
    title: str
    content: str
    sort_order: int


class UserProfileSchema(BaseModel):
    """The effective display name plus every user-authored profile card."""

    model_config = ConfigDict(frozen=True)

    display_name: str
    cards: list[UserProfileCardSchema]


class UserProfileCardInputSchema(BaseModel):
    """One card in a full profile replacement."""

    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=120)
    content: str = Field(min_length=1, max_length=2000)


class UserProfileUpdateSchema(BaseModel):
    """Replace the display name and every profile card in one transaction."""

    model_config = ConfigDict(extra="forbid")

    display_name: str = Field(min_length=1, max_length=80)
    cards: list[UserProfileCardInputSchema] = Field(default_factory=list, max_length=20)
