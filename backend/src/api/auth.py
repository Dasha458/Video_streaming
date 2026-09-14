from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse, RedirectResponse

from src.api.dependencies.services import get_auth_service, get_github_oauth_service
from src.config import get_github_oauth_settings
from src.infrastructure.auth import (
    current_active_user,
    current_superuser,
    fastapi_users,
    get_jwt_strategy,
)
from src.models import User
from src.schemas.user import (
    CheckUserRequest,
    CheckUserResponse,
    LoginRequest,
    LoginResponse,
    PasswordChangeRequest,
    UserCreate,
    UserPublic,
    UserRead,
    UserUpdateRequest,
)
from src.services.auth_service import AuthService
from src.services.github_oauth_service import GitHubOAuthService

_github_settings = get_github_oauth_settings()

router_auth = APIRouter(
    prefix="/api/auth",
    tags=["auth"],
    default_response_class=JSONResponse,
    responses={
        404: {"description": "Not found"},
        500: {"description": "Internal server error"},
    },
)

# Include fastapi-users register router
router_auth.include_router(
    fastapi_users.get_register_router(UserRead, UserCreate),
)

# Include fastapi-users reset password router
router_auth.include_router(
    fastapi_users.get_reset_password_router(),
)

# Include fastapi-users verify router
router_auth.include_router(
    fastapi_users.get_verify_router(UserRead),
)


@router_auth.post("/login", response_model=LoginResponse)
async def login(
    data: LoginRequest,
    auth_service: AuthService = Depends(get_auth_service),
) -> LoginResponse:
    user = await auth_service.login(data.email, data.password)
    strategy = get_jwt_strategy()
    token = await strategy.write_token(user)
    return LoginResponse(token=token)


@router_auth.post("/logout")
async def logout() -> dict:
    return {"detail": "Logged out"}


@router_auth.get("/me", response_model=UserPublic)
async def get_me(user: User = Depends(current_active_user)) -> UserPublic:
    return UserPublic.model_validate(user)


@router_auth.patch("/me", response_model=UserPublic)
async def update_me(
    data: UserUpdateRequest,
    user: User = Depends(current_active_user),
    auth_service: AuthService = Depends(get_auth_service),
) -> UserPublic:
    user = await auth_service.update_username(user, data.username)
    return UserPublic.model_validate(user)


@router_auth.post("/me/change-password", status_code=204)
async def change_password(
    data: PasswordChangeRequest,
    user: User = Depends(current_active_user),
    auth_service: AuthService = Depends(get_auth_service),
) -> None:
    await auth_service.change_password(
        user, data.current_password, data.new_password
    )


@router_auth.get("/admin")
async def admin_panel(user: User = Depends(current_superuser)) -> dict:
    return {"msg": f"Hello Admin {user.username}"}


@router_auth.post("/check-user", response_model=CheckUserResponse)
async def check_user(
    data: CheckUserRequest,
    auth_service: AuthService = Depends(get_auth_service),
) -> CheckUserResponse:
    username_exists, email_exists = await auth_service.check_user_exists(
        data.username, data.email
    )
    return CheckUserResponse(
        username_exists=username_exists,
        email_exists=email_exists,
    )


@router_auth.get("/users/{username}", response_model=UserPublic)
async def get_user_by_username(
    username: str,
    auth_service: AuthService = Depends(get_auth_service),
) -> UserPublic:
    user = await auth_service.get_user_by_username(username)
    return UserPublic.model_validate(user)


# ── GitHub OAuth ──────────────────────────────────────────────────────────────


@router_auth.get("/github/authorize")
async def github_authorize(
    github_oauth_service: GitHubOAuthService = Depends(get_github_oauth_service),
) -> dict:
    """Return the GitHub authorization URL for the frontend to redirect to."""
    authorization_url = await github_oauth_service.build_authorization_url()
    return {"authorization_url": authorization_url}


@router_auth.get("/github/callback")
async def github_callback(
    code: str = Query(...),
    state: str = Query(...),
    github_oauth_service: GitHubOAuthService = Depends(get_github_oauth_service),
) -> RedirectResponse:
    """Exchange GitHub OAuth code for a JWT and redirect to the frontend."""
    github_oauth_service.validate_state(state)
    user = await github_oauth_service.exchange_code_for_user(code)

    strategy = get_jwt_strategy()
    jwt_token = await strategy.write_token(user)

    frontend_url = _github_settings.FRONTEND_URL
    return RedirectResponse(url=f"{frontend_url}/auth/callback?token={jwt_token}")
