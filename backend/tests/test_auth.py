"""Tests for /api/auth/* endpoints."""

import uuid
from unittest.mock import AsyncMock, MagicMock
from urllib.parse import parse_qs, urlparse

import pytest

from tests.conftest import TEST_USER_EMAIL, TEST_USER_USERNAME


def _result(value):
    """A stand-in for a SQLAlchemy Result.

    `.unique()` returns the same object, as the real one does. The old
    mocks answered scalar_one_or_none() directly and nothing else, so a
    query that failed to call .unique() -- which a real User query must,
    because oauth_accounts is a joined eager load -- passed here and
    raised against the database.
    """
    result = MagicMock()
    result.unique.return_value = result
    result.scalar_one_or_none.return_value = value
    return result


class TestRegisterEndpoint:
    """POST /api/auth/register — handled by fastapi-users router."""

    def test_empty_body_returns_error(self, client):
        # fastapi-users returns 400 (not 422) for validation errors
        response = client.post("/api/auth/register", json={})
        assert response.status_code in (400, 422)

    def test_missing_username_returns_error(self, client):
        response = client.post(
            "/api/auth/register",
            json={"email": "new@example.com", "password": "StrongPass123!"},
        )
        assert response.status_code in (400, 422)

    def test_missing_password_returns_error(self, client):
        response = client.post(
            "/api/auth/register",
            json={"email": "new@example.com", "username": "newuser"},
        )
        assert response.status_code in (400, 422)

    def test_missing_email_returns_error(self, client):
        response = client.post(
            "/api/auth/register",
            json={"password": "StrongPass123!", "username": "newuser"},
        )
        assert response.status_code in (400, 422)

    def test_register_route_is_reachable(self, client, app):
        """Route is wired: a valid-format body reaches user manager logic."""
        from src.infrastructure.auth import get_user_manager

        mock_manager = AsyncMock()
        # Simulate duplicate user error (fastapi-users raises HTTPException 400)
        from fastapi import HTTPException

        mock_manager.create = AsyncMock(
            side_effect=HTTPException(
                status_code=400, detail="REGISTER_USER_ALREADY_EXISTS"
            )
        )
        app.dependency_overrides[get_user_manager] = lambda: mock_manager
        try:
            response = client.post(
                "/api/auth/register",
                json={
                    "email": "test@example.com",
                    "password": "StrongPass123!",
                    "username": "someuser",
                },
            )
            # 400 or 500 — proves the route was reached (not 422 which means schema error)
            assert response.status_code in (400, 500)
        finally:
            app.dependency_overrides.pop(get_user_manager, None)


class TestLoginEndpoint:
    """POST /api/auth/login."""

    def test_empty_body_returns_422(self, client):
        response = client.post("/api/auth/login", json={})
        assert response.status_code == 400  # app maps ValidationError → 400

    def test_missing_password_returns_422(self, client):
        response = client.post("/api/auth/login", json={"email": TEST_USER_EMAIL})
        assert response.status_code == 400  # app maps ValidationError → 400

    def test_wrong_credentials_returns_400(self, client, app):
        from src.infrastructure.auth import get_user_manager

        mock_manager = AsyncMock()
        mock_manager.authenticate = AsyncMock(return_value=None)
        app.dependency_overrides[get_user_manager] = lambda: mock_manager
        try:
            response = client.post(
                "/api/auth/login",
                json={"email": "wrong@example.com", "password": "wrongpass"},
            )
            assert response.status_code == 400
        finally:
            app.dependency_overrides.pop(get_user_manager, None)

    def test_inactive_user_returns_400(self, client, app):
        from src.infrastructure.auth import get_user_manager

        inactive = MagicMock()
        inactive.is_active = False
        mock_manager = AsyncMock()
        mock_manager.authenticate = AsyncMock(return_value=inactive)
        app.dependency_overrides[get_user_manager] = lambda: mock_manager
        try:
            response = client.post(
                "/api/auth/login",
                json={"email": TEST_USER_EMAIL, "password": "pass"},
            )
            assert response.status_code == 400
        finally:
            app.dependency_overrides.pop(get_user_manager, None)

    def test_valid_credentials_set_httponly_cookie_not_body(
        self, client, app, mock_user
    ):
        from src.infrastructure.auth import get_user_manager

        mock_manager = AsyncMock()
        mock_manager.authenticate = AsyncMock(return_value=mock_user)
        app.dependency_overrides[get_user_manager] = lambda: mock_manager
        try:
            response = client.post(
                "/api/auth/login",
                json={"email": TEST_USER_EMAIL, "password": "correctpassword"},
            )
            assert response.status_code == 204
            assert response.content == b""  # token must never be in the body
            set_cookie = response.headers["set-cookie"]
            assert set_cookie.startswith("access_token=")
            assert "HttpOnly" in set_cookie
            assert "SameSite=lax" in set_cookie
            assert len(response.cookies["access_token"]) > 20
        finally:
            app.dependency_overrides.pop(get_user_manager, None)


class TestLogoutEndpoint:
    """POST /api/auth/logout — must clear the cookie even without a valid session."""

    def test_clears_cookie_unauthenticated(self, client, app):
        from src.infrastructure.auth import current_active_user

        original = app.dependency_overrides.pop(current_active_user, None)
        try:
            response = client.post("/api/auth/logout")
            assert response.status_code == 204
            set_cookie = response.headers["set-cookie"]
            assert set_cookie.startswith('access_token=""')
            assert "Max-Age=0" in set_cookie
        finally:
            if original is not None:
                app.dependency_overrides[current_active_user] = original


class TestGetMeEndpoint:
    """GET /api/auth/me — requires current_active_user."""

    def test_returns_200_with_user_data(self, client):
        response = client.get("/api/auth/me")
        assert response.status_code == 200
        body = response.json()
        assert body["email"] == TEST_USER_EMAIL
        assert body["username"] == TEST_USER_USERNAME

    def test_unauthenticated_returns_401(self, client, app):
        from src.infrastructure.auth import current_active_user

        original = app.dependency_overrides.pop(current_active_user, None)
        try:
            response = client.get("/api/auth/me")
            assert response.status_code == 401
        finally:
            if original is not None:
                app.dependency_overrides[current_active_user] = original


class TestCheckUserEndpoint:
    """POST /api/auth/check-user."""

    def test_empty_body_returns_422(self, client):
        response = client.post("/api/auth/check-user", json={})
        assert response.status_code == 400  # app maps ValidationError → 400

    def test_username_and_email_free(self, client, app):
        from src.infrastructure import get_async_session

        session = AsyncMock()
        result_free = _result(None)
        session.execute = AsyncMock(return_value=result_free)
        original = app.dependency_overrides.get(get_async_session)
        app.dependency_overrides[get_async_session] = lambda: session
        try:
            response = client.post(
                "/api/auth/check-user",
                json={"username": "freeuser", "email": "free@example.com"},
            )
            assert response.status_code == 200
            body = response.json()
            assert body["username_exists"] is False
            assert body["email_exists"] is False
        finally:
            if original is not None:
                app.dependency_overrides[get_async_session] = original
            else:
                app.dependency_overrides.pop(get_async_session, None)

    def test_username_taken(self, client, app, mock_user):
        from src.infrastructure import get_async_session

        session = AsyncMock()
        taken = _result(mock_user)
        free = _result(None)
        session.execute = AsyncMock(side_effect=[taken, free])
        original = app.dependency_overrides.get(get_async_session)
        app.dependency_overrides[get_async_session] = lambda: session
        try:
            response = client.post(
                "/api/auth/check-user",
                json={"username": TEST_USER_USERNAME, "email": "other@example.com"},
            )
            assert response.status_code == 200
            body = response.json()
            assert body["username_exists"] is True
            assert body["email_exists"] is False
        finally:
            if original is not None:
                app.dependency_overrides[get_async_session] = original
            else:
                app.dependency_overrides.pop(get_async_session, None)

    def test_email_taken(self, client, app, mock_user):
        from src.infrastructure import get_async_session

        session = AsyncMock()
        free = _result(None)
        taken = _result(mock_user)
        session.execute = AsyncMock(side_effect=[free, taken])
        original = app.dependency_overrides.get(get_async_session)
        app.dependency_overrides[get_async_session] = lambda: session
        try:
            response = client.post(
                "/api/auth/check-user",
                json={"username": "newuser", "email": TEST_USER_EMAIL},
            )
            assert response.status_code == 200
            body = response.json()
            assert body["username_exists"] is False
            assert body["email_exists"] is True
        finally:
            if original is not None:
                app.dependency_overrides[get_async_session] = original
            else:
                app.dependency_overrides.pop(get_async_session, None)


class TestGetUserByUsernameEndpoint:
    """GET /api/auth/users/{username}."""

    def test_existing_user_returns_200(self, client, app, mock_user):
        from src.infrastructure import get_async_session

        session = AsyncMock()
        result = _result(mock_user)
        session.execute = AsyncMock(return_value=result)
        original = app.dependency_overrides.get(get_async_session)
        app.dependency_overrides[get_async_session] = lambda: session
        try:
            response = client.get(f"/api/auth/users/{TEST_USER_USERNAME}")
            assert response.status_code == 200
            assert response.json()["username"] == TEST_USER_USERNAME
        finally:
            if original is not None:
                app.dependency_overrides[get_async_session] = original
            else:
                app.dependency_overrides.pop(get_async_session, None)

    def test_nonexistent_user_returns_404(self, client, app):
        from src.infrastructure import get_async_session

        session = AsyncMock()
        result = _result(None)
        session.execute = AsyncMock(return_value=result)
        original = app.dependency_overrides.get(get_async_session)
        app.dependency_overrides[get_async_session] = lambda: session
        try:
            response = client.get("/api/auth/users/ghost_xyz_123")
            assert response.status_code == 404
        finally:
            if original is not None:
                app.dependency_overrides[get_async_session] = original
            else:
                app.dependency_overrides.pop(get_async_session, None)


class TestGitHubAuthorizeEndpoint:
    """GET /api/auth/github/authorize."""

    def test_returns_authorization_url(self, client):
        response = client.get("/api/auth/github/authorize")
        assert response.status_code == 200
        body = response.json()
        assert "authorization_url" in body
        assert "github.com" in body["authorization_url"]

    def test_binds_the_flow_to_this_browser_with_a_cookie(self, client):
        """Without it the state proves only that we issued one, not that we
        issued it to whoever is finishing the flow."""
        response = client.get("/api/auth/github/authorize")
        set_cookie = response.headers["set-cookie"]
        assert set_cookie.startswith("github_oauth_state=")
        assert "HttpOnly" in set_cookie
        # Lax, not Strict: the callback is a top-level navigation from
        # GitHub, and Strict would strip the cookie from it.
        assert "SameSite=lax" in set_cookie.lower().replace(
            "samesite=lax", "SameSite=lax"
        )

    def test_the_state_in_the_url_matches_the_cookie(self, client):
        import jwt as pyjwt

        response = client.get("/api/auth/github/authorize")
        url = response.json()["authorization_url"]
        state = parse_qs(urlparse(url).query)["state"][0]
        claims = pyjwt.decode(state, options={"verify_signature": False})

        assert claims["csrf"] == response.cookies["github_oauth_state"]
        # It used to carry no expiry, so a state stayed good forever.
        assert claims["exp"] > claims["iat"]


class TestGitHubCallbackEndpoint:
    """GET /api/auth/github/callback — CSRF validation."""

    def test_a_state_without_its_cookie_is_refused(self, client):
        """The attack this closes: start a flow yourself, take the valid
        state and code it produces, and have someone else finish it --
        which signed them into your account."""
        authorize = client.get("/api/auth/github/authorize")
        state = parse_qs(urlparse(authorize.json()["authorization_url"]).query)[
            "state"
        ][0]
        client.cookies.clear()

        response = client.get(
            "/api/auth/github/callback",
            params={"code": "somecode", "state": state},
            follow_redirects=False,
        )
        assert response.status_code == 400

    def test_a_state_with_someone_elses_cookie_is_refused(self, client):
        authorize = client.get("/api/auth/github/authorize")
        state = parse_qs(urlparse(authorize.json()["authorization_url"]).query)[
            "state"
        ][0]
        client.cookies.set("github_oauth_state", "not-the-one-we-issued")

        response = client.get(
            "/api/auth/github/callback",
            params={"code": "somecode", "state": state},
            follow_redirects=False,
        )
        assert response.status_code == 400

    def test_invalid_state_returns_400(self, client):
        response = client.get(
            "/api/auth/github/callback",
            params={"code": "somecode", "state": "invalid-jwt-state"},
        )
        assert response.status_code == 400

    def test_missing_code_returns_422(self, client):
        response = client.get(
            "/api/auth/github/callback",
            params={"state": "somestate"},
        )
        assert response.status_code == 400  # app maps ValidationError → 400

    def test_the_state_cookie_is_cleared_once_the_flow_is_done(
        self, client, app, mock_user
    ):
        """One flow, one state."""
        from src.api.dependencies.services import get_github_oauth_service

        mock_service = AsyncMock()
        mock_service.validate_state = lambda state, cookie: None
        mock_service.exchange_code_for_user = AsyncMock(return_value=mock_user)
        app.dependency_overrides[get_github_oauth_service] = lambda: mock_service
        try:
            response = client.get(
                "/api/auth/github/callback",
                params={"code": "ok", "state": "ok"},
                follow_redirects=False,
            )
            cookies = response.headers.get_list("set-cookie")
            cleared = [c for c in cookies if c.startswith("github_oauth_state=")]
            assert cleared, "the state cookie is not cleared"
            assert 'github_oauth_state=""' in cleared[0] or "Max-Age=0" in cleared[0]
        finally:
            app.dependency_overrides.pop(get_github_oauth_service, None)

    def test_success_sets_cookie_and_keeps_token_out_of_the_url(
        self, client, app, mock_user
    ):
        from src.api.dependencies.services import get_github_oauth_service

        mock_service = AsyncMock()
        mock_service.validate_state = lambda state, cookie: None
        mock_service.exchange_code_for_user = AsyncMock(return_value=mock_user)
        app.dependency_overrides[get_github_oauth_service] = lambda: mock_service
        try:
            response = client.get(
                "/api/auth/github/callback",
                params={"code": "ok", "state": "ok"},
                follow_redirects=False,
            )
            assert response.status_code == 307
            location = response.headers["location"]
            assert location.endswith("/auth/callback")
            assert "token=" not in location
            # Two cookies now: the session, and the state being cleared.
            session = next(
                c
                for c in response.headers.get_list("set-cookie")
                if c.startswith("access_token=")
            )
            assert "HttpOnly" in session
        finally:
            app.dependency_overrides.pop(get_github_oauth_service, None)


_TEST_JWT_SECRET = "0123456789abcdef0123456789abcdef0123456789abcdef"


class TestOAuthStateBinding:
    """GitHubOAuthService.validate_state — the rule itself.

    A signature proves the server issued some state. It does not prove the
    server issued *this* state to *this* browser, which is what stops an
    attacker starting a flow and having someone else complete it.
    """

    @staticmethod
    def _service():
        from src.config import GitHubOAuthSettings, JWTSettings
        from src.services.github_oauth_service import GitHubOAuthService

        return GitHubOAuthService(
            session=AsyncMock(),
            github_oauth_client=AsyncMock(),
            github_settings=GitHubOAuthSettings(
                GITHUB_CLIENT_ID="id",
                GITHUB_CLIENT_SECRET="secret",
                GITHUB_CALLBACK_URL="http://localhost/api/auth/github/callback",
                FRONTEND_URL="http://localhost",
            ),
            jwt_settings=JWTSettings(JWT_SECRET=_TEST_JWT_SECRET),
        )

    def _state(self, csrf: str, **overrides) -> str:
        import time

        import jwt as pyjwt

        now = int(time.time())
        claims = {"csrf": csrf, "iat": now, "exp": now + 600}
        claims.update(overrides)
        return pyjwt.encode(claims, _TEST_JWT_SECRET, algorithm="HS256")

    def test_a_matching_cookie_passes(self):
        self._service().validate_state(self._state("abc"), "abc")

    def test_no_cookie_is_refused(self):
        from src.errors.auth import InvalidOAuthStateError

        with pytest.raises(InvalidOAuthStateError):
            self._service().validate_state(self._state("abc"), None)

    def test_a_different_cookie_is_refused(self):
        from src.errors.auth import InvalidOAuthStateError

        with pytest.raises(InvalidOAuthStateError):
            self._service().validate_state(self._state("abc"), "xyz")

    def test_an_expired_state_is_refused(self):
        import time

        from src.errors.auth import InvalidOAuthStateError

        past = int(time.time()) - 10
        with pytest.raises(InvalidOAuthStateError):
            self._service().validate_state(
                self._state("abc", exp=past, iat=past - 600), "abc"
            )

    def test_a_state_without_an_expiry_is_refused(self):
        """It used to carry none, so one stayed good forever."""
        import jwt as pyjwt

        from src.errors.auth import InvalidOAuthStateError

        no_exp = pyjwt.encode({"csrf": "abc"}, _TEST_JWT_SECRET, algorithm="HS256")
        with pytest.raises(InvalidOAuthStateError):
            self._service().validate_state(no_exp, "abc")

    def test_a_state_signed_by_someone_else_is_refused(self):
        import time

        import jwt as pyjwt

        from src.errors.auth import InvalidOAuthStateError

        now = int(time.time())
        forged = pyjwt.encode(
            {"csrf": "abc", "iat": now, "exp": now + 600},
            "not-our-secret",
            algorithm="HS256",
        )
        with pytest.raises(InvalidOAuthStateError):
            self._service().validate_state(forged, "abc")


class TestPasswordPolicy:
    """UserManager.validate_password.

    There was none: fastapi-users' default accepts anything, no schema set
    a minimum, and change-password hashed whatever it was handed. "a" was
    a valid password.
    """

    @staticmethod
    def _manager():
        from src.infrastructure.auth import UserManager

        return UserManager(AsyncMock())

    @staticmethod
    def _user(email="someone@example.com", username="someone"):
        user = MagicMock()
        user.email = email
        user.username = username
        return user

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "password", ["", "a", "short7c"], ids=["empty", "one", "seven"]
    )
    async def test_too_short_is_refused(self, password):
        from fastapi_users.exceptions import InvalidPasswordException

        with pytest.raises(InvalidPasswordException):
            await self._manager().validate_password(password, self._user())

    @pytest.mark.asyncio
    async def test_eight_characters_is_enough(self):
        await self._manager().validate_password("eightchr", self._user())

    @pytest.mark.asyncio
    async def test_the_email_itself_is_refused(self):
        """A long password that is still the worst possible one."""
        from fastapi_users.exceptions import InvalidPasswordException

        with pytest.raises(InvalidPasswordException):
            await self._manager().validate_password("someone@example.com", self._user())

    @pytest.mark.asyncio
    async def test_the_username_itself_is_refused(self):
        from fastapi_users.exceptions import InvalidPasswordException

        with pytest.raises(InvalidPasswordException):
            await self._manager().validate_password(
                "loginname", self._user(username="loginname")
            )

    @pytest.mark.asyncio
    async def test_case_does_not_get_round_it(self):
        from fastapi_users.exceptions import InvalidPasswordException

        with pytest.raises(InvalidPasswordException):
            await self._manager().validate_password("SomeOne@Example.COM", self._user())


class TestChangePasswordGoesThroughThePolicy:
    """It used to hash whatever it was handed, so a password rejected at
    sign-up could be set a minute later."""

    @pytest.mark.asyncio
    async def test_a_weak_new_password_is_refused(self):
        from src.errors.auth import WeakPasswordError
        from src.services.auth_service import AuthService

        user = MagicMock()
        user.email = "someone@example.com"
        user.username = "someone"

        manager = AsyncMock()
        manager.authenticate = AsyncMock(return_value=user)
        from src.infrastructure.auth import UserManager

        manager.validate_password = UserManager(AsyncMock()).validate_password

        service = AuthService(session=AsyncMock(), user_manager=manager)
        with pytest.raises(WeakPasswordError):
            await service.change_password(user, "current", "a")

        manager.password_helper.hash.assert_not_called()


class TestSessionsEndWhenThePasswordChanges:
    """Tokens were stateless and tied to nothing.

    Changing the password left every session issued before it valid for
    the rest of the hour, on every device -- including whoever's access
    prompted the change. People change their password precisely because
    somebody else may have it.
    """

    @staticmethod
    def _user(hashed: str):

        user = MagicMock()
        user.id = uuid.UUID("11111111-1111-1111-1111-111111111111")
        user.hashed_password = hashed
        return user

    @staticmethod
    def _manager(user):
        manager = AsyncMock()
        manager.parse_id = lambda value: uuid.UUID(value)
        manager.get = AsyncMock(return_value=user)
        return manager

    @pytest.mark.asyncio
    async def test_a_token_still_works_while_the_password_is_unchanged(self):
        from src.infrastructure.auth import get_jwt_strategy

        strategy = get_jwt_strategy()
        user = self._user("hash-one")
        token = await strategy.write_token(user)

        assert await strategy.read_token(token, self._manager(user)) is user

    @pytest.mark.asyncio
    async def test_the_same_token_stops_working_once_it_changes(self):
        from src.infrastructure.auth import get_jwt_strategy

        strategy = get_jwt_strategy()
        token = await strategy.write_token(self._user("hash-one"))

        # The stored hash is now a different one -- the password changed.
        changed = self._user("hash-two")

        assert await strategy.read_token(token, self._manager(changed)) is None

    @pytest.mark.asyncio
    async def test_a_token_from_before_this_existed_is_refused(self):
        """It carries no binding, so nothing says it survived a change."""
        from fastapi_users.jwt import generate_jwt

        from src.infrastructure.auth import TOKEN_LIFETIME_SECONDS, get_jwt_strategy

        strategy = get_jwt_strategy()
        user = self._user("hash-one")
        legacy = generate_jwt(
            {"sub": str(user.id), "aud": strategy.token_audience},
            strategy.encode_key,
            TOKEN_LIFETIME_SECONDS,
            algorithm=strategy.algorithm,
        )

        assert await strategy.read_token(legacy, self._manager(user)) is None

    @pytest.mark.asyncio
    async def test_the_fingerprint_says_nothing_about_the_password(self):
        from src.infrastructure.auth import password_fingerprint

        marked = password_fingerprint("$2b$12$averyrealbcrypthash")

        assert "$2b$" not in marked
        assert len(marked) == 16
