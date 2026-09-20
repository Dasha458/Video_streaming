import uuid
from typing import AsyncGenerator, Optional

from fastapi import Depends, Request, Response
from fastapi_users import BaseUserManager, FastAPIUsers, UUIDIDMixin
from fastapi_users.authentication import (
    AuthenticationBackend,
    CookieTransport,
    JWTStrategy,
)
from fastapi_users_db_sqlalchemy import SQLAlchemyUserDatabase
from httpx_oauth.clients.github import GitHubOAuth2
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import get_github_oauth_settings, get_jwt_settings
from src.infrastructure.database import get_async_session
from src.models import User

_github_settings = get_github_oauth_settings()
github_oauth_client = GitHubOAuth2(
    client_id=_github_settings.GITHUB_CLIENT_ID,
    client_secret=_github_settings.GITHUB_CLIENT_SECRET,
)

jwt_settings = get_jwt_settings()


async def get_user_db(
    session: AsyncSession = Depends(get_async_session),
) -> AsyncGenerator[SQLAlchemyUserDatabase, None]:
    yield SQLAlchemyUserDatabase(session, User)


class UserManager(UUIDIDMixin, BaseUserManager[User, uuid.UUID]):
    """
    KNOWN GAP (tracked, not a bug to "fix" here): on_after_forgot_password and
    on_after_request_verify never send an email. fastapi-users still issues a
    valid reset/verification token and the /forgot-password and /request-verify
    endpoints respond 202 as if the email went out, but the user never
    receives it -- password reset and email verification are non-functional
    end-to-end until a real email provider (SMTP/SendGrid/SES/etc.) is wired
    in here. That's a product/infra decision (which provider, credentials,
    templates), not a cleanup task -- deliberately left as-is.
    """

    reset_password_token_secret = jwt_settings.JWT_SECRET
    verification_token_secret = jwt_settings.JWT_SECRET

    async def on_after_register(
        self, user: User, request: Optional[Request] = None
    ) -> None:
        pass

    async def on_after_forgot_password(
        self, user: User, token: str, request: Optional[Request] = None
    ) -> None:
        # See the class docstring: email delivery is not implemented yet.
        pass

    async def on_after_request_verify(
        self, user: User, token: str, request: Optional[Request] = None
    ) -> None:
        # See the class docstring: email delivery is not implemented yet.
        pass


async def get_user_manager(
    user_db: SQLAlchemyUserDatabase = Depends(get_user_db),
) -> AsyncGenerator[UserManager, None]:
    yield UserManager(user_db)


TOKEN_LIFETIME_SECONDS = 3600

# The JWT travels only in an httpOnly cookie: JavaScript can't read it, so an
# XSS foothold can't exfiltrate the session the way it could from localStorage.
# SameSite=Lax keeps the cookie off cross-site POSTs (CSRF) while still sending
# it on same-site requests -- which localhost:5173 -> localhost:8000 is, since
# SameSite compares registrable domain, not port. `secure` follows the
# deployment scheme: FRONTEND_URL is the one place that knows whether the
# app is served over https.
cookie_transport = CookieTransport(
    cookie_name="access_token",
    cookie_max_age=TOKEN_LIFETIME_SECONDS,
    cookie_secure=_github_settings.FRONTEND_URL.startswith("https://"),
    cookie_httponly=True,
    cookie_samesite="lax",
)


def set_access_cookie(response: Response, token: str) -> Response:
    """Attach the session cookie to any response (login, OAuth redirect)."""
    response.set_cookie(
        key=cookie_transport.cookie_name,
        value=token,
        max_age=cookie_transport.cookie_max_age,
        path=cookie_transport.cookie_path,
        domain=cookie_transport.cookie_domain,
        secure=cookie_transport.cookie_secure,
        httponly=cookie_transport.cookie_httponly,
        samesite=cookie_transport.cookie_samesite,
    )
    return response


def clear_access_cookie(response: Response) -> Response:
    response.set_cookie(
        key=cookie_transport.cookie_name,
        value="",
        max_age=0,
        path=cookie_transport.cookie_path,
        domain=cookie_transport.cookie_domain,
        secure=cookie_transport.cookie_secure,
        httponly=cookie_transport.cookie_httponly,
        samesite=cookie_transport.cookie_samesite,
    )
    return response


def get_jwt_strategy() -> JWTStrategy:
    return JWTStrategy(
        secret=jwt_settings.JWT_SECRET, lifetime_seconds=TOKEN_LIFETIME_SECONDS
    )


auth_backend = AuthenticationBackend(
    name="jwt",
    transport=cookie_transport,
    get_strategy=get_jwt_strategy,
)

fastapi_users = FastAPIUsers[User, uuid.UUID](get_user_manager, [auth_backend])

current_active_user = fastapi_users.current_user(active=True)
current_optional_user = fastapi_users.current_user(active=True, optional=True)
current_superuser = fastapi_users.current_user(active=True, superuser=True)
