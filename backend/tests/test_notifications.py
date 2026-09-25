"""Tests for /api/notifications/* endpoints."""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock

from tests.conftest import TEST_USER_ID

FAKE_NOTIFICATION_ID = uuid.UUID("ffffffff-ffff-ffff-ffff-ffffffffffff")


def _make_notification():
    from src.schemas.notification import NotificationResponse

    return NotificationResponse(
        id=FAKE_NOTIFICATION_ID,
        content="Someone liked your video",
        link="/watch?v=123",
        notification_type="like",
        is_read=False,
        created_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
    )


class TestGetNotificationsEndpoint:
    """GET /api/notifications."""

    def test_returns_200_empty_list(self, client, app):
        from src.api.dependencies.services import get_notification_service
        from src.schemas.notification import NotificationsPage

        svc = AsyncMock()
        svc.list = AsyncMock(
            return_value=NotificationsPage(items=[], unread_count=0, total=0)
        )
        app.dependency_overrides[get_notification_service] = lambda: svc
        try:
            response = client.get("/api/notifications")
            assert response.status_code == 200
            body = response.json()
            assert body["items"] == []
            assert body["unread_count"] == 0
        finally:
            app.dependency_overrides.pop(get_notification_service, None)

    def test_returns_paginated_list(self, client, app):
        from src.api.dependencies.services import get_notification_service
        from src.schemas.notification import NotificationsPage

        svc = AsyncMock()
        svc.list = AsyncMock(
            return_value=NotificationsPage(
                items=[_make_notification()], unread_count=1, total=1
            )
        )
        app.dependency_overrides[get_notification_service] = lambda: svc
        try:
            response = client.get("/api/notifications?page=1&size=20")
            assert response.status_code == 200
            body = response.json()
            assert len(body["items"]) == 1
            assert body["unread_count"] == 1
            svc.list.assert_awaited_once_with(TEST_USER_ID, 1, 20)
        finally:
            app.dependency_overrides.pop(get_notification_service, None)

    def test_unauthenticated_returns_401(self, client, app):
        from src.infrastructure.auth import current_active_user

        original = app.dependency_overrides.pop(current_active_user, None)
        try:
            response = client.get("/api/notifications")
            assert response.status_code == 401
        finally:
            if original is not None:
                app.dependency_overrides[current_active_user] = original


class TestMarkNotificationReadEndpoint:
    """PUT /api/notifications/{notification_id}/read."""

    def test_mark_read_returns_204(self, client, app):
        from src.api.dependencies.services import get_notification_service

        svc = AsyncMock()
        svc.mark_read = AsyncMock(return_value=None)
        app.dependency_overrides[get_notification_service] = lambda: svc
        try:
            response = client.put(f"/api/notifications/{FAKE_NOTIFICATION_ID}/read")
            assert response.status_code == 204
            svc.mark_read.assert_awaited_once_with(TEST_USER_ID, FAKE_NOTIFICATION_ID)
        finally:
            app.dependency_overrides.pop(get_notification_service, None)

    def test_not_found_returns_404(self, client, app):
        from src.api.dependencies.services import get_notification_service
        from src.errors.notifications import NotificationNotFoundError

        svc = AsyncMock()
        svc.mark_read = AsyncMock(side_effect=NotificationNotFoundError())
        app.dependency_overrides[get_notification_service] = lambda: svc
        try:
            response = client.put(f"/api/notifications/{FAKE_NOTIFICATION_ID}/read")
            assert response.status_code == 404
        finally:
            app.dependency_overrides.pop(get_notification_service, None)


class TestMarkAllNotificationsReadEndpoint:
    """PUT /api/notifications/read-all."""

    def test_mark_all_read_returns_204(self, client, app):
        from src.api.dependencies.services import get_notification_service

        svc = AsyncMock()
        svc.mark_all_read = AsyncMock(return_value=None)
        app.dependency_overrides[get_notification_service] = lambda: svc
        try:
            response = client.put("/api/notifications/read-all")
            assert response.status_code == 204
            svc.mark_all_read.assert_awaited_once_with(TEST_USER_ID)
        finally:
            app.dependency_overrides.pop(get_notification_service, None)


class TestUnreadCountEndpoint:
    """GET /api/notifications/unread-count."""

    def test_returns_count(self, client, app):
        from src.api.dependencies.services import get_notification_service
        from src.schemas.notification import NotificationsPage

        svc = AsyncMock()
        svc.list = AsyncMock(
            return_value=NotificationsPage(items=[], unread_count=4, total=10)
        )
        app.dependency_overrides[get_notification_service] = lambda: svc
        try:
            response = client.get("/api/notifications/unread-count")
            assert response.status_code == 200
            assert response.json()["count"] == 4
        finally:
            app.dependency_overrides.pop(get_notification_service, None)
