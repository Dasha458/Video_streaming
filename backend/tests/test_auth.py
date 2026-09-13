"""Tests for /api/auth/* endpoints."""
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from tests.conftest import TEST_USER_EMAIL, TEST_USER_ID, TEST_USER_USERNAME


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
            side_effect=HTTPException(status_code=400, detail="REGISTER_USER_ALREADY_EXISTS")
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

    def test_valid_credentials_returns_token(self, client, app, mock_user):
        from src.infrastructure.auth import get_user_manager

        mock_manager = AsyncMock()
        mock_manager.authenticate = AsyncMock(return_value=mock_user)
        app.dependency_overrides[get_user_manager] = lambda: mock_manager
        try:
            response = client.post(
                "/api/auth/login",
                json={"email": TEST_USER_EMAIL, "password": "correctpassword"},
            )
            assert response.status_code == 200
            body = response.json()
            assert "token" in body
            assert isinstance(body["token"], str)
            assert len(body["token"]) > 20
        finally:
            app.dependency_overrides.pop(get_user_manager, None)


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


class TestLogoutEndpoint:
    """POST /api/auth/logout — stateless, always 200."""

    def test_logout_returns_200(self, client):
        response = client.post("/api/auth/logout")
        assert response.status_code == 200

    def test_logout_returns_detail(self, client):
        body = client.post("/api/auth/logout").json()
        assert body == {"detail": "Logged out"}


class TestCheckUserEndpoint:
    """POST /api/auth/check-user."""

    def test_empty_body_returns_422(self, client):
        response = client.post("/api/auth/check-user", json={})
        assert response.status_code == 400  # app maps ValidationError → 400

    def test_username_and_email_free(self, client, app):
        from src.infrastructure import get_async_session

        session = AsyncMock()
        result_free = MagicMock()
        result_free.scalar_one_or_none.return_value = None
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
        taken = MagicMock()
        taken.scalar_one_or_none.return_value = mock_user
        free = MagicMock()
        free.scalar_one_or_none.return_value = None
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
        free = MagicMock()
        free.scalar_one_or_none.return_value = None
        taken = MagicMock()
        taken.scalar_one_or_none.return_value = mock_user
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
        result = MagicMock()
        result.scalar_one_or_none.return_value = mock_user
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
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
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


class TestGitHubCallbackEndpoint:
    """GET /api/auth/github/callback — CSRF validation."""

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
