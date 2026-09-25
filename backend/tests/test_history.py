"""Tests for /api/history/* endpoints."""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock

from tests.conftest import TEST_USER_ID

FAKE_VIDEO_ID = uuid.UUID("dddddddd-dddd-dddd-dddd-dddddddddddd")


def _make_item():
    from src.schemas.history import HistoryVideoItem

    return HistoryVideoItem(
        id=FAKE_VIDEO_ID,
        title="Watched Video",
        thumbnail="/thumb.jpg",
        channel_name="TestChannel",
        channel_avatar="/av.jpg",
        views_count=5,
        created_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
        last_watched_at=datetime(2025, 1, 2, tzinfo=timezone.utc),
    )


class TestGetHistoryEndpoint:
    """GET /api/history."""

    def test_returns_200_empty_list(self, client, app):
        from src.api.dependencies.services import get_history_service

        svc = AsyncMock()
        svc.list = AsyncMock(return_value=([], 0))
        app.dependency_overrides[get_history_service] = lambda: svc
        try:
            response = client.get("/api/history")
            assert response.status_code == 200
            body = response.json()
            assert body["items"] == []
            assert body["total"] == 0
        finally:
            app.dependency_overrides.pop(get_history_service, None)

    def test_returns_paginated_list(self, client, app):
        from src.api.dependencies.services import get_history_service

        svc = AsyncMock()
        svc.list = AsyncMock(return_value=([_make_item()], 1))
        app.dependency_overrides[get_history_service] = lambda: svc
        try:
            response = client.get("/api/history?page=1&size=20")
            assert response.status_code == 200
            body = response.json()
            assert len(body["items"]) == 1
            assert body["items"][0]["title"] == "Watched Video"
            svc.list.assert_awaited_once_with(TEST_USER_ID, 1, 20)
        finally:
            app.dependency_overrides.pop(get_history_service, None)

    def test_unauthenticated_returns_401(self, client, app):
        from src.infrastructure.auth import current_active_user

        original = app.dependency_overrides.pop(current_active_user, None)
        try:
            response = client.get("/api/history")
            assert response.status_code == 401
        finally:
            if original is not None:
                app.dependency_overrides[current_active_user] = original


class TestClearHistoryEndpoint:
    """DELETE /api/history."""

    def test_clear_returns_204(self, client, app):
        from src.api.dependencies.services import get_history_service

        svc = AsyncMock()
        svc.clear = AsyncMock(return_value=None)
        app.dependency_overrides[get_history_service] = lambda: svc
        try:
            response = client.delete("/api/history")
            assert response.status_code == 204
            svc.clear.assert_awaited_once_with(TEST_USER_ID)
        finally:
            app.dependency_overrides.pop(get_history_service, None)


class TestRemoveFromHistoryEndpoint:
    """DELETE /api/history/{video_id}."""

    def test_remove_returns_204(self, client, app):
        from src.api.dependencies.services import get_history_service

        svc = AsyncMock()
        svc.remove = AsyncMock(return_value=None)
        app.dependency_overrides[get_history_service] = lambda: svc
        try:
            response = client.delete(f"/api/history/{FAKE_VIDEO_ID}")
            assert response.status_code == 204
            svc.remove.assert_awaited_once_with(TEST_USER_ID, FAKE_VIDEO_ID)
        finally:
            app.dependency_overrides.pop(get_history_service, None)

    def test_not_found_returns_404(self, client, app):
        from src.api.dependencies.services import get_history_service
        from src.errors.history import HistoryEntryNotFoundError

        svc = AsyncMock()
        svc.remove = AsyncMock(side_effect=HistoryEntryNotFoundError())
        app.dependency_overrides[get_history_service] = lambda: svc
        try:
            response = client.delete(f"/api/history/{FAKE_VIDEO_ID}")
            assert response.status_code == 404
        finally:
            app.dependency_overrides.pop(get_history_service, None)
