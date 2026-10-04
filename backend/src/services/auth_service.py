from fastapi.security import OAuth2PasswordRequestForm
from fastapi_users.exceptions import InvalidPasswordException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.errors.auth import (
    IncorrectPasswordError,
    InvalidCredentialsError,
    UsernameEmptyError,
    UsernameTakenError,
    UserNotFoundError,
    WeakPasswordError,
)
from src.infrastructure.auth import UserManager
from src.models import User


class AuthService:
    def __init__(self, session: AsyncSession, user_manager: UserManager):
        self.session = session
        self.user_manager = user_manager

    async def login(self, email: str, password: str) -> User:
        user = await self.user_manager.authenticate(
            credentials=OAuth2PasswordRequestForm(username=email, password=password)
        )
        if user is None or not user.is_active:
            raise InvalidCredentialsError()
        return user

    async def update_username(self, user: User, new_username: str | None) -> User:
        if new_username is not None:
            name = new_username.strip()
            if not name:
                raise UsernameEmptyError()
            # .unique() is required on any User result: oauth_accounts is
            # a joined eager load (fastapi-users needs it that way), and
            # SQLAlchemy refuses to collapse the duplicated rows unless
            # asked. Without it this raised InvalidRequestError the moment
            # a row actually matched -- so "that username is taken" was an
            # internal error instead.
            taken = await self.session.execute(
                select(User).where(User.username == name, User.id != user.id)  # type: ignore[arg-type]
            )
            existing = taken.unique().scalar_one_or_none()
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
            OAuth2PasswordRequestForm(username=user.email, password=current_password)
        )
        if authenticated is None:
            raise IncorrectPasswordError()

        # The same policy registration goes through. This used to hash
        # whatever it was handed, so a password rejected at sign-up could
        # be set here a minute later.
        try:
            await self.user_manager.validate_password(new_password, user)
        except InvalidPasswordException as e:
            raise WeakPasswordError(str(e.reason)) from e

        user.hashed_password = self.user_manager.password_helper.hash(new_password)
        await self.session.commit()

    async def check_user_exists(self, username: str, email: str) -> tuple[bool, bool]:
        username_result = await self.session.execute(
            select(User).where(User.username == username)
        )
        email_result = await self.session.execute(
            select(User).where(User.email == email)  # type: ignore[arg-type]
        )
        # See update_username: a User result has to be uniquified.
        return (
            username_result.unique().scalar_one_or_none() is not None,
            email_result.unique().scalar_one_or_none() is not None,
        )

    async def get_user_by_username(self, username: str) -> User:
        result = await self.session.execute(
            select(User).where(User.username == username)
        )
        user = result.unique().scalar_one_or_none()
        if not user:
            raise UserNotFoundError()
        return user
