"""
Which GitHub address is allowed to decide who you are.

The address returned by the OAuth flow decides which account the person
is signed into: an existing user with the same email is linked rather
than a new one created. So it has to be an address GitHub says belongs
to them.

It used to prefer `github_data["email"]` -- the public profile field,
which a user sets to anything they like and GitHub does not verify in
this sense -- and consulted the verified list only when that field was
empty. Setting a GitHub profile email to somebody else's address was
therefore enough to be signed in as them here.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.errors.auth import GitHubEmailNotFoundError, GitHubUserInfoError


def _response(status_code: int, payload):
    response = MagicMock()
    response.status_code = status_code
    response.json = MagicMock(return_value=payload)
    return response


def _service(profile, emails, emails_status=200):
    """A service whose only live part is the HTTP client."""
    from src.services.github_oauth_service import GitHubOAuthService

    client = AsyncMock()
    client.get = AsyncMock(
        side_effect=[
            _response(200, profile),
            _response(emails_status, emails),
        ]
    )
    context = MagicMock()
    context.__aenter__ = AsyncMock(return_value=client)
    context.__aexit__ = AsyncMock(return_value=False)

    service = GitHubOAuthService.__new__(GitHubOAuthService)
    return service, context


async def _email(profile, emails, emails_status=200) -> str:
    import src.services.github_oauth_service as module

    service, context = _service(profile, emails, emails_status)
    original = module.httpx.AsyncClient
    module.httpx.AsyncClient = MagicMock(return_value=context)
    try:
        _, email = await service._fetch_github_user_email("token")
        return email
    finally:
        module.httpx.AsyncClient = original


VICTIM = "someone.else@example.com"
MINE = "me@example.com"


class TestOnlyVerifiedAddressesCount:
    @pytest.mark.asyncio
    async def test_an_unverified_profile_email_is_not_used(self):
        """The takeover: the profile field claims the victim's address,
        and the account GitHub actually verified is a different one."""
        email = await _email(
            profile={"id": 1, "login": "attacker", "email": VICTIM},
            emails=[
                {"email": VICTIM, "primary": False, "verified": False},
                {"email": MINE, "primary": True, "verified": True},
            ],
        )

        assert email == MINE

    @pytest.mark.asyncio
    async def test_a_verified_profile_email_is_honoured(self):
        """Their own choice, and GitHub vouches for it."""
        chosen = "chosen@example.com"
        email = await _email(
            profile={"id": 1, "login": "someone", "email": chosen},
            emails=[
                {"email": MINE, "primary": True, "verified": True},
                {"email": chosen, "primary": False, "verified": True},
            ],
        )

        assert email == chosen

    @pytest.mark.asyncio
    async def test_the_primary_verified_address_is_the_default(self):
        email = await _email(
            profile={"id": 1, "login": "someone", "email": None},
            emails=[
                {"email": "secondary@example.com", "primary": False, "verified": True},
                {"email": MINE, "primary": True, "verified": True},
            ],
        )

        assert email == MINE

    @pytest.mark.asyncio
    async def test_an_account_with_nothing_verified_is_refused(self):
        with pytest.raises(GitHubEmailNotFoundError):
            await _email(
                profile={"id": 1, "login": "someone", "email": VICTIM},
                emails=[{"email": VICTIM, "primary": True, "verified": False}],
            )

    @pytest.mark.asyncio
    async def test_the_profile_email_is_no_substitute_for_the_list(self):
        """If the verified list cannot be read, there is no address worth
        trusting -- the profile field was the fallback before."""
        with pytest.raises(GitHubEmailNotFoundError):
            await _email(
                profile={"id": 1, "login": "someone", "email": VICTIM},
                emails={"message": "Bad credentials"},
                emails_status=403,
            )

    @pytest.mark.asyncio
    async def test_a_profile_that_cannot_be_read_is_an_error(self):
        import src.services.github_oauth_service as module

        service, context = _service({}, [])
        context.__aenter__.return_value.get = AsyncMock(
            side_effect=[_response(401, {}), _response(200, [])]
        )
        original = module.httpx.AsyncClient
        module.httpx.AsyncClient = MagicMock(return_value=context)
        try:
            with pytest.raises(GitHubUserInfoError):
                await service._fetch_github_user_email("token")
        finally:
            module.httpx.AsyncClient = original
