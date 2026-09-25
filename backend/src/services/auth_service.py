from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.errors.auth import (
    IncorrectPasswordError,
    InvalidCredentialsError,
    UsernameEmptyError,
    UsernameTakenError,
    UserNotFoundError,
)
from src.infrastructure.auth import UserManager
from src.models import User


class _Credentials:
    """Minimal object satisfying fastapi-users' authenticate(credentials=...) interface."""

    __slots__ = ("username", "password")

    def __init__(self, username: str, password: str):
        self.username = username
        self.password = password


class AuthService:
    def __init__(self, session: AsyncSession, user_manager: UserManager):
        self.session = session
        self.user_manager = user_manager

    async def login(self, email: str, password: str) -> User:
        user = await self.user_manager.authenticate(
            credentials=_Credentials(email, password)
        )
        if user is None or not user.is_active:
            raise InvalidCredentialsError()
        return user

    async def update_username(self, user: User, new_username: str | None) -> User:
        if new_username is not None:
            name = new_username.strip()
            if not name:
                raise UsernameEmptyError()
            existing = await self.session.scalar(
                select(User).where(User.username == name, User.id != user.id)
            )
            if existing:
                raise UsernameTakenError()
            user.username = name
        await self.session.commit()
        await self.session.refresh(user)
        return user

    async def change_password(
        self, user: User, current_password: str, new_password: str
    ) -> None:
        authenticated = await self.user_manager.authenticate(
            _Credentials(user.email, current_password)
        )
        if authenticated is None:
            raise IncorrectPasswordError()
        user.hashed_password = self.user_manager.password_helper.hash(new_password)
        await self.session.commit()

    async def check_user_exists(self, username: str, email: str) -> tuple[bool, bool]:
        username_result = await self.session.execute(
            select(User).where(User.username == username)
        )
        email_result = await self.session.execute(
            select(User).where(User.email == email)
        )
        return (
            username_result.scalar_one_or_none() is not None,
            email_result.scalar_one_or_none() is not None,
        )

    async def get_user_by_username(self, username: str) -> User:
        result = await self.session.execute(
            select(User).where(User.username == username)
        )
        user = result.scalar_one_or_none()
        if not user:
            raise UserNotFoundError()
        return user
