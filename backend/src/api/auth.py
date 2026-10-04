from fastapi import APIRouter, Depends, Query, Request, Response
from fastapi.responses import JSONResponse, RedirectResponse

from src.api.dependencies.services import get_auth_service, get_github_oauth_service
from src.config import get_github_oauth_settings
from src.infrastructure.auth import (
    clear_access_cookie,
    cookie_transport,
    current_active_user,
    current_superuser,
    fastapi_users,
    get_jwt_strategy,
    set_access_cookie,
)
from src.models import User
from src.schemas.user import (
    CheckUserRequest,
    CheckUserResponse,
    LoginRequest,
    PasswordChangeRequest,
    UserCreate,
    UserPublic,
    UserRead,
    UserUpdateRequest,
)
from src.services.auth_service import AuthService
from src.services.github_oauth_service import (
    STATE_COOKIE_NAME,
    STATE_TTL_SECONDS,
    GitHubOAuthService,
)

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


@router_auth.post("/login", status_code=204, response_class=Response)
async def login(
    data: LoginRequest,
    auth_service: AuthService = Depends(get_auth_service),
) -> Response:
    """Set the httpOnly session cookie; the token never reaches JavaScript."""
    user = await auth_service.login(data.email, data.password)
    token = await get_jwt_strategy().write_token(user)
    return set_access_cookie(Response(status_code=204), token)


@router_auth.post("/logout", status_code=204, response_class=Response)
async def logout() -> Response:
    # Deliberately unauthenticated: an expired cookie must still be clearable.
    return clear_access_cookie(Response(status_code=204))


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


@router_auth.post("/me/change-password", status_code=204, response_class=Response)
async def change_password(
    data: PasswordChangeRequest,
    user: User = Depends(current_active_user),
    auth_service: AuthService = Depends(get_auth_service),
) -> Response:
    """Change the password and end every other session.

    Sessions are bound to the password they were issued under, so this
    makes every token handed out earlier stop working -- on every device.
    That is the point: people change their password because somebody else
    may have it.

    The browser doing the changing is given a new cookie, so the one
    person who is certainly entitled to stay signed in does.
    """
    await auth_service.change_password(user, data.current_password, data.new_password)
    token = await get_jwt_strategy().write_token(user)
    return set_access_cookie(Response(status_code=204), token)


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
) -> JSONResponse:
    """The GitHub authorization URL, plus the cookie that binds it here.

    The cookie is what makes the state mean something: without it a valid
    state proves only that this server issued one, not that it issued this
    one to this browser.
    """
    authorization_url, csrf = await github_oauth_service.build_authorization_url()
    response = JSONResponse(content={"authorization_url": authorization_url})
    response.set_cookie(
        key=STATE_COOKIE_NAME,
        value=csrf,
        max_age=STATE_TTL_SECONDS,
        httponly=True,
        secure=cookie_transport.cookie_secure,
        # Lax, not Strict: the callback arrives as a top-level navigation
        # from GitHub, which Strict would strip the cookie from.
        samesite="lax",
        path="/",
    )
    return response


@router_auth.get("/github/callback")
async def github_callback(
    request: Request,
    code: str = Query(...),
    state: str = Query(...),
    github_oauth_service: GitHubOAuthService = Depends(get_github_oauth_service),
) -> RedirectResponse:
    """Exchange the GitHub code for a session cookie and redirect to the frontend.

    The token rides on the redirect as a Set-Cookie header, never in the URL --
    a query-string token would land in browser history, server access logs
    and any Referer header the callback page happens to emit.
    """
    github_oauth_service.validate_state(state, request.cookies.get(STATE_COOKIE_NAME))
    user = await github_oauth_service.exchange_code_for_user(code)
    token = await get_jwt_strategy().write_token(user)

    response = RedirectResponse(url=f"{_github_settings.FRONTEND_URL}/auth/callback")
    # One flow, one state.
    response.delete_cookie(STATE_COOKIE_NAME, path="/")
    return set_access_cookie(response, token)
