"""HTTP adapters for accounts and cookie sessions."""

from fastapi import APIRouter, Depends, Request, Response, status

from app.dependency.auth import get_current_user, require_authenticated
from app.infrastructure.config.settings import Settings
from app.module.auth.dependencies import (
    get_auth_service,
    get_auth_settings,
    get_cookie_token,
)
from app.module.auth.schema.auth_schema import (
    AuthResponseSchema,
    AuthStatusSchema,
    ChangePasswordSchema,
    LoginSchema,
    SetupSchema,
    UserProfileSchema,
    UserProfileUpdateSchema,
    UserSchema,
)
from app.module.auth.service.auth_service import AuthService

router = APIRouter(prefix="/auth", tags=["auth"])


def _set_session_cookie(response: Response, token: str, settings: Settings) -> None:
    response.set_cookie(
        key=settings.cookie_name,
        value=token,
        max_age=settings.session_ttl_hours * 3600,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
    )


@router.get("/status", response_model=AuthStatusSchema, operation_id="getAuthStatus")
async def get_auth_status(
    token: str | None = Depends(get_cookie_token),
    service: AuthService = Depends(get_auth_service),
) -> AuthStatusSchema:
    """Public endpoint used by the login gate."""
    return await service.status(token)


@router.post(
    "/setup",
    response_model=AuthResponseSchema,
    status_code=status.HTTP_201_CREATED,
    operation_id="setupAccount",
)
async def setup_account(
    payload: SetupSchema,
    response: Response,
    settings: Settings = Depends(get_auth_settings),
    service: AuthService = Depends(get_auth_service),
) -> AuthResponseSchema:
    """Create the owner account on the first run and sign it in."""
    user, token = await service.setup(
        username=payload.username,
        password=payload.password,
        confirm_password=payload.confirm_password,
    )
    _set_session_cookie(response, token, settings)
    return AuthResponseSchema(user=user)


@router.post("/login", response_model=AuthResponseSchema, operation_id="login")
async def login(
    payload: LoginSchema,
    request: Request,
    response: Response,
    settings: Settings = Depends(get_auth_settings),
    service: AuthService = Depends(get_auth_service),
) -> AuthResponseSchema:
    """Verify a password and issue a new session cookie."""
    remote_address = request.client.host if request.client else "unknown"
    user, token = await service.login(
        username=payload.username,
        password=payload.password,
        remote_address=remote_address,
    )
    _set_session_cookie(response, token, settings)
    return AuthResponseSchema(user=user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT, operation_id="logout")
async def logout(
    response: Response,
    token: str | None = Depends(get_cookie_token),
    settings: Settings = Depends(get_auth_settings),
    service: AuthService = Depends(get_auth_service),
) -> Response:
    """Delete the server session and clear the browser cookie."""
    await service.logout(token)
    response.delete_cookie(
        key=settings.cookie_name,
        path="/",
        secure=settings.cookie_secure,
        httponly=True,
        samesite="lax",
    )
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@router.post(
    "/password",
    status_code=status.HTTP_204_NO_CONTENT,
    operation_id="changePassword",
)
async def change_password(
    payload: ChangePasswordSchema,
    user: UserSchema = Depends(get_current_user),
    token: str | None = Depends(get_cookie_token),
    service: AuthService = Depends(get_auth_service),
) -> None:
    """Change the signed-in password; allowed while a change is forced."""
    await service.change_password(
        user_id=user.user_id,
        current_password=payload.current_password,
        new_password=payload.new_password,
        confirm_password=payload.confirm_password,
        current_token=token,
    )


@router.get("/me", response_model=UserSchema, operation_id="getCurrentUser")
async def get_me(
    user: UserSchema = Depends(require_authenticated),
) -> UserSchema:
    """Return the signed-in account."""
    return user


@router.get(
    "/profile",
    response_model=UserProfileSchema,
    operation_id="getUserProfile",
)
async def get_profile(
    user: UserSchema = Depends(require_authenticated),
    service: AuthService = Depends(get_auth_service),
) -> UserProfileSchema:
    """Return the display name and every ordered user profile card."""
    return await service.get_profile(user.user_id)


@router.put(
    "/profile",
    response_model=UserProfileSchema,
    operation_id="updateUserProfile",
)
async def update_profile(
    payload: UserProfileUpdateSchema,
    user: UserSchema = Depends(require_authenticated),
    service: AuthService = Depends(get_auth_service),
) -> UserProfileSchema:
    """Replace the display name and every profile card atomically."""
    return await service.update_profile(user.user_id, payload)
