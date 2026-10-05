"""
Real-Postgres tests for creating the account behind a GitHub sign-in.

The username was looked up and then inserted -- two steps with a gap in
between. Two sign-ups arriving together both found the name free, and
the second got an IntegrityError and a 500 at the end of an otherwise
successful GitHub sign-in.

The savepoint is the part that matters: an IntegrityError poisons the
transaction, so without one the retry fails on the broken session rather
than on the name.
"""

from unittest.mock import MagicMock

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.errors.auth import GitHubUsernameUnavailableError
from src.models import User
from src.services.github_oauth_service import GitHubOAuthService
from tests.integration.conftest import make_user

pytestmark = pytest.mark.integration


def _service(session: AsyncSession) -> GitHubOAuthService:
    service = GitHubOAuthService.__new__(GitHubOAuthService)
    service.session = session
    service.github_oauth_client = MagicMock()
    service.github_settings = MagicMock()
    service.jwt_settings = MagicMock()
    return service


@pytest.mark.asyncio
async def test_the_github_login_is_used_when_it_is_free(session: AsyncSession):
    user = await _service(session)._create_user("new@example.com", "octocat", "1234567")

    assert user.username == "octocat"
    assert user.email == "new@example.com"


@pytest.mark.asyncio
async def test_a_taken_username_does_not_fail_the_sign_in(session: AsyncSession):
    """This was a 500 at the end of a successful GitHub round trip."""
    await make_user(session, username="octocat")

    user = await _service(session)._create_user("new@example.com", "octocat", "1234567")

    assert user.username == "octocat_123456"


@pytest.mark.asyncio
async def test_it_keeps_going_past_the_second_collision(session: AsyncSession):
    await make_user(session, username="octocat")
    await make_user(session, username="octocat_123456")

    user = await _service(session)._create_user("new@example.com", "octocat", "1234567")

    assert user.username == "octocat_1234567"


@pytest.mark.asyncio
async def test_the_transaction_survives_a_collision(session: AsyncSession):
    await make_user(session, username="octocat")

    await _service(session)._create_user("new@example.com", "octocat", "1234567")

    # Still usable: without a savepoint the IntegrityError would have
    # poisoned it and taken the rest of the sign-in with it.
    remaining = await session.scalar(select(func.count()).select_from(User))
    assert remaining is not None and remaining > 0


@pytest.mark.asyncio
async def test_the_same_email_arriving_twice_returns_the_first_account(
    session: AsyncSession,
):
    """Two sign-ins racing: the second finds the row the first wrote
    rather than failing on the unique email."""
    first = await make_user(session, username="someone")
    first.email = "shared@example.com"
    await session.flush()

    second = await _service(session)._create_user(
        "shared@example.com", "otherlogin", "9999999"
    )

    assert second.id == first.id


@pytest.mark.asyncio
async def test_every_candidate_taken_says_so(session: AsyncSession):
    for name in ("octocat", "octocat_123456", "octocat_1234567"):
        await make_user(session, username=name)

    with pytest.raises(GitHubUsernameUnavailableError):
        await _service(session)._create_user("new@example.com", "octocat", "1234567")
