"""Tests for /api/liked/* endpoints."""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock

from tests.conftest import TEST_USER_ID

FAKE_VIDEO_ID = uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")


def _make_preview():
    from src.schemas.video import VideoPreview

    return VideoPreview(
        id=FAKE_VIDEO_ID,
        title="Liked Video",
        thumbnail="/thumb.jpg",
        channel_avatar="/av.jpg",
        channel_name="TestChannel",
        views_count=10,
        likes_count=3,
        dislikes_count=0,
        privacy="public",
        status="Ready",
        created_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
    )


class TestGetLikedVideosEndpoint:
    """GET /api/liked."""

    def test_returns_200_empty_list(self, client, app):
        from src.api.dependencies.services import get_liked_service

        svc = AsyncMock()
        svc.list_liked = AsyncMock(return_value=([], 0))
        app.dependency_overrides[get_liked_service] = lambda: svc
        try:
            response = client.get("/api/liked")
            assert response.status_code == 200
            body = response.json()
            assert body["items"] == []
            assert body["total"] == 0
        finally:
            app.dependency_overrides.pop(get_liked_service, None)

    def test_returns_paginated_list(self, client, app):
        from src.api.dependencies.services import get_liked_service

        svc = AsyncMock()
        svc.list_liked = AsyncMock(return_value=([_make_preview()], 1))
        app.dependency_overrides[get_liked_service] = lambda: svc
        try:
            response = client.get("/api/liked?page=1&size=20")
            assert response.status_code == 200
            body = response.json()
            assert len(body["items"]) == 1
            assert body["items"][0]["title"] == "Liked Video"
            assert body["total"] == 1
            svc.list_liked.assert_awaited_once_with(TEST_USER_ID, 1, 20)
        finally:
            app.dependency_overrides.pop(get_liked_service, None)

    def test_unauthenticated_returns_401(self, client, app):
        from src.infrastructure.auth import current_active_user

        original = app.dependency_overrides.pop(current_active_user, None)
        try:
            response = client.get("/api/liked")
            assert response.status_code == 401
        finally:
            if original is not None:
                app.dependency_overrides[current_active_user] = original
