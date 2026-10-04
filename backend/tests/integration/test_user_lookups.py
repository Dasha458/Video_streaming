"""
Real-Postgres tests for looking a user up.

`User.oauth_accounts` is a joined eager load -- fastapi-users needs it
that way -- so every row of a User query comes back once per joined row,
and SQLAlchemy refuses to collapse them unless `.unique()` is called. A
query without it raises InvalidRequestError the moment a row actually
matches.

Which means these lookups worked only while they found nothing. "Is this
username taken?" answered correctly for a free name and raised for a
taken one; a public profile could not be opened; a GitHub sign-in could
not be linked to an existing account. Every test of them used a mocked
session, where the restriction does not exist.
"""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.errors.auth import UsernameTakenError, UserNotFoundError
from src.services.auth_service import AuthService
from tests.integration.conftest import make_user

pytestmark = pytest.mark.integration


def _service(session: AsyncSession) -> AuthService:
    from unittest.mock import AsyncMock

    service = AuthService.__new__(AuthService)
    service.session = session
    service.user_manager = AsyncMock()
    return service


@pytest.mark.asyncio
async def test_a_profile_that_exists_can_be_opened(session: AsyncSession):
    await make_user(session, username="visible")

    found = await _service(session).get_user_by_username("visible")

    assert found.username == "visible"


@pytest.mark.asyncio
async def test_a_profile_that_does_not_exist_is_not_found(session: AsyncSession):
    with pytest.raises(UserNotFoundError):
        await _service(session).get_user_by_username("nobody-by-that-name")


@pytest.mark.asyncio
async def test_check_user_reports_both_as_taken(session: AsyncSession):
    user = await make_user(session, username="registered")
    user.email = "registered@example.com"
    await session.flush()

    username_taken, email_taken = await _service(session).check_user_exists(
        "registered", "registered@example.com"
    )

    assert (username_taken, email_taken) == (True, True)


@pytest.mark.asyncio
async def test_check_user_reports_a_free_name_as_free(session: AsyncSession):
    username_taken, email_taken = await _service(session).check_user_exists(
        "unclaimed", "unclaimed@example.com"
    )

    assert (username_taken, email_taken) == (False, False)


@pytest.mark.asyncio
async def test_renaming_onto_a_taken_username_is_refused(session: AsyncSession):
    """It used to raise an internal error instead of saying the name was
    taken -- the refusal only worked when the name was free."""
    await make_user(session, username="occupied")
    renamer = await make_user(session, username="renamer")

    with pytest.raises(UsernameTakenError):
        await _service(session).update_username(renamer, "occupied")


@pytest.mark.asyncio
async def test_renaming_to_a_free_username_works(session: AsyncSession):
    renamer = await make_user(session, username="before")

    updated = await _service(session).update_username(renamer, "after")

    assert updated.username == "after"


@pytest.mark.asyncio
async def test_keeping_your_own_name_is_not_a_collision(session: AsyncSession):
    """The query excludes the user doing the renaming; with the result
    uniquified, that exclusion is actually reached."""
    user = await make_user(session, username="unchanged")

    updated = await _service(session).update_username(user, "unchanged")

    assert updated.username == "unchanged"
