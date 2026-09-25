"""Tests for /api/watch-later/* endpoints."""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock

from tests.conftest import TEST_USER_ID

FAKE_VIDEO_ID = uuid.UUID("eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee")


def _make_item():
    from src.schemas.watch_later import WatchLaterVideoItem

    return WatchLaterVideoItem(
        id=FAKE_VIDEO_ID,
        title="Saved Video",
        thumbnail="/thumb.jpg",
        channel_name="TestChannel",
        channel_avatar="/av.jpg",
        views_count=7,
        created_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
        added_at=datetime(2025, 1, 2, tzinfo=timezone.utc),
    )


class TestGetWatchLaterEndpoint:
    """GET /api/watch-later."""

    def test_returns_200_empty_list(self, client, app):
        from src.api.dependencies.services import get_watch_later_service

        svc = AsyncMock()
        svc.list = AsyncMock(return_value=([], 0))
        app.dependency_overrides[get_watch_later_service] = lambda: svc
        try:
            response = client.get("/api/watch-later")
            assert response.status_code == 200
            body = response.json()
            assert body["items"] == []
            assert body["total"] == 0
        finally:
            app.dependency_overrides.pop(get_watch_later_service, None)

    def test_returns_paginated_list(self, client, app):
        from src.api.dependencies.services import get_watch_later_service

        svc = AsyncMock()
        svc.list = AsyncMock(return_value=([_make_item()], 1))
        app.dependency_overrides[get_watch_later_service] = lambda: svc
        try:
            response = client.get("/api/watch-later?page=1&size=20")
            assert response.status_code == 200
            body = response.json()
            assert len(body["items"]) == 1
            assert body["items"][0]["title"] == "Saved Video"
            svc.list.assert_awaited_once_with(TEST_USER_ID, 1, 20)
        finally:
            app.dependency_overrides.pop(get_watch_later_service, None)

    def test_unauthenticated_returns_401(self, client, app):
        from src.infrastructure.auth import current_active_user

        original = app.dependency_overrides.pop(current_active_user, None)
        try:
            response = client.get("/api/watch-later")
            assert response.status_code == 401
        finally:
            if original is not None:
                app.dependency_overrides[current_active_user] = original


class TestAddToWatchLaterEndpoint:
    """POST /api/watch-later/{video_id}."""

    def test_add_returns_204(self, client, app):
        from src.api.dependencies.services import get_watch_later_service

        svc = AsyncMock()
        svc.add = AsyncMock(return_value=None)
        app.dependency_overrides[get_watch_later_service] = lambda: svc
        try:
            response = client.post(f"/api/watch-later/{FAKE_VIDEO_ID}")
            assert response.status_code == 204
            svc.add.assert_awaited_once_with(TEST_USER_ID, FAKE_VIDEO_ID)
        finally:
            app.dependency_overrides.pop(get_watch_later_service, None)

    def test_duplicate_returns_409(self, client, app):
        from src.api.dependencies.services import get_watch_later_service
        from src.errors.watch_later import AlreadyInWatchLaterError

        svc = AsyncMock()
        svc.add = AsyncMock(side_effect=AlreadyInWatchLaterError())
        app.dependency_overrides[get_watch_later_service] = lambda: svc
        try:
            response = client.post(f"/api/watch-later/{FAKE_VIDEO_ID}")
            assert response.status_code == 409
        finally:
            app.dependency_overrides.pop(get_watch_later_service, None)


class TestClearWatchLaterEndpoint:
    """DELETE /api/watch-later."""

    def test_clear_returns_204(self, client, app):
        from src.api.dependencies.services import get_watch_later_service

        svc = AsyncMock()
        svc.clear = AsyncMock(return_value=None)
        app.dependency_overrides[get_watch_later_service] = lambda: svc
        try:
            response = client.delete("/api/watch-later")
            assert response.status_code == 204
            svc.clear.assert_awaited_once_with(TEST_USER_ID)
        finally:
            app.dependency_overrides.pop(get_watch_later_service, None)


class TestRemoveFromWatchLaterEndpoint:
    """DELETE /api/watch-later/{video_id}."""

    def test_remove_returns_204(self, client, app):
        from src.api.dependencies.services import get_watch_later_service

        svc = AsyncMock()
        svc.remove = AsyncMock(return_value=None)
        app.dependency_overrides[get_watch_later_service] = lambda: svc
        try:
            response = client.delete(f"/api/watch-later/{FAKE_VIDEO_ID}")
            assert response.status_code == 204
            svc.remove.assert_awaited_once_with(TEST_USER_ID, FAKE_VIDEO_ID)
        finally:
            app.dependency_overrides.pop(get_watch_later_service, None)

    def test_not_found_returns_404(self, client, app):
        from src.api.dependencies.services import get_watch_later_service
        from src.errors.watch_later import WatchLaterEntryNotFoundError

        svc = AsyncMock()
        svc.remove = AsyncMock(side_effect=WatchLaterEntryNotFoundError())
        app.dependency_overrides[get_watch_later_service] = lambda: svc
        try:
            response = client.delete(f"/api/watch-later/{FAKE_VIDEO_ID}")
            assert response.status_code == 404
        finally:
            app.dependency_overrides.pop(get_watch_later_service, None)
