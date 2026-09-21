import secrets

import bcrypt
import httpx
import jwt as pyjwt
from httpx_oauth.clients.github import GitHubOAuth2
from httpx_oauth.oauth2 import GetAccessTokenError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import GitHubOAuthSettings, JWTSettings
from src.errors.auth import (
    GitHubCodeExchangeError,
    GitHubEmailNotFoundError,
    GitHubUserInfoError,
    InvalidOAuthStateError,
    UserNotFoundError,
)
from src.models import OAuthAccount, User

GITHUB_OAUTH_NAME = "github"


class GitHubOAuthService:
    def __init__(
        self,
        session: AsyncSession,
        github_oauth_client: GitHubOAuth2,
        github_settings: GitHubOAuthSettings,
        jwt_settings: JWTSettings,
    ):
        self.session = session
        self.github_oauth_client = github_oauth_client
        self.github_settings = github_settings
        self.jwt_settings = jwt_settings

    async def build_authorization_url(self) -> str:
        state = pyjwt.encode(
            {"csrf": secrets.token_urlsafe(16)},
            self.jwt_settings.JWT_SECRET,
            algorithm="HS256",
        )
        return await self.github_oauth_client.get_authorization_url(
            redirect_uri=self.github_settings.GITHUB_CALLBACK_URL,
            state=state,
            scope=["user:email"],
        )

    def validate_state(self, state: str) -> None:
        try:
            pyjwt.decode(state, self.jwt_settings.JWT_SECRET, algorithms=["HS256"])
        except pyjwt.PyJWTError as e:
            raise InvalidOAuthStateError() from e

    async def _fetch_github_user_email(self, access_token: str) -> tuple[dict, str]:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                "https://api.github.com/user",
                headers={
                    "Authorization": f"token {access_token}",
                    "Accept": "application/json",
                },
            )
            if resp.status_code != 200:
                raise GitHubUserInfoError()
            github_data = resp.json()

            email = github_data.get("email")
            if not email:
                emails_resp = await client.get(
                    "https://api.github.com/user/emails",
                    headers={
                        "Authorization": f"token {access_token}",
                        "Accept": "application/json",
                    },
                )
                if emails_resp.status_code == 200:
                    for entry in emails_resp.json():
                        if entry.get("primary") and entry.get("verified"):
                            email = entry["email"]
                            break

        if not email:
            raise GitHubEmailNotFoundError()

        return github_data, email

    async def exchange_code_for_user(self, code: str) -> User:
        try:
            token_data = await self.github_oauth_client.get_access_token(
                code=code,
                redirect_uri=self.github_settings.GITHUB_CALLBACK_URL,
            )
        except (GetAccessTokenError, httpx.HTTPError) as e:
            raise GitHubCodeExchangeError() from e

        access_token = token_data["access_token"]
        github_data, email = await self._fetch_github_user_email(access_token)

        github_id = str(github_data["id"])
        github_login = github_data.get("login", f"user_{github_id}")

        oauth_result = await self.session.execute(
            select(OAuthAccount).where(
                OAuthAccount.oauth_name == GITHUB_OAUTH_NAME,
                OAuthAccount.account_id == github_id,
            )
        )
        oauth_account = oauth_result.scalar_one_or_none()

        if oauth_account:
            linked_user = await self.session.get(User, oauth_account.user_id)
            if linked_user is None:
                raise UserNotFoundError()
            return linked_user

        user_result = await self.session.execute(
            select(User).where(User.email == email)
        )
        user = user_result.scalar_one_or_none()

        if not user:
            username = github_login
            taken = await self.session.execute(
                select(User).where(User.username == username)
            )
            if taken.scalar_one_or_none():
                username = f"{github_login}_{github_id[:6]}"

            user = User(
                email=email,
                username=username,
                hashed_password=bcrypt.hashpw(
                    secrets.token_bytes(32), bcrypt.gensalt()
                ).decode(),
                is_active=True,
                is_superuser=False,
                is_verified=True,
            )
            self.session.add(user)
            await self.session.flush()

        new_oauth = OAuthAccount(
            oauth_name=GITHUB_OAUTH_NAME,
            access_token=access_token,
            account_id=github_id,
            account_email=email,
            user_id=user.id,
        )
        self.session.add(new_oauth)
        await self.session.commit()
        return user
