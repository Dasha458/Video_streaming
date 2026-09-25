"""Tests for /api/videos/* endpoints."""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock

FAKE_VIDEO_ID = uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")


def _make_preview(vid_id=FAKE_VIDEO_ID, title="Test Video"):
    from src.schemas.video import VideoPreview

    return VideoPreview(
        id=vid_id,
        title=title,
        thumbnail="/thumb.jpg",
        channel_avatar="/av.jpg",
        channel_name="TestChannel",
        views_count=42,
        likes_count=5,
        dislikes_count=1,
        privacy="public",
        status="Ready",
        created_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
    )


def _make_playback(vid_id=FAKE_VIDEO_ID):
    from src.schemas.video import VideoPlayback

    return VideoPlayback(
        id=vid_id,
        name="Test Video",
        description="A test video",
        privacy="public",
        created_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
        resolutions=["360p", "720p", "1080p"],
        thumbnail_url="/thumb.jpg",
        avatar_url="/av.jpg",
        channel_name="TestChannel",
        likes_count=10,
        dislikes_count=2,
        views_count=100,
        master_hls_url="http://minio/master.m3u8",
    )


class TestListVideosEndpoint:
    """GET /api/videos/"""

    def test_returns_200_empty_list(self, client, app):
        from src.api.dependencies.services import get_video_service

        svc = AsyncMock()
        svc.list_videos = AsyncMock(return_value=([], 0))
        app.dependency_overrides[get_video_service] = lambda: svc
        try:
            response = client.get("/api/videos/")
            assert response.status_code == 200
            body = response.json()
            assert body["items"] == []
            assert body["total"] == 0
            assert body["page"] == 1
        finally:
            app.dependency_overrides.pop(get_video_service, None)

    def test_returns_paginated_list(self, client, app):
        from src.api.dependencies.services import get_video_service

        svc = AsyncMock()
        svc.list_videos = AsyncMock(return_value=([_make_preview()], 1))
        app.dependency_overrides[get_video_service] = lambda: svc
        try:
            response = client.get("/api/videos/?page=1&size=20")
            assert response.status_code == 200
            body = response.json()
            assert len(body["items"]) == 1
            assert body["total"] == 1
            assert body["items"][0]["title"] == "Test Video"
            assert body["items"][0]["views_count"] == 42
        finally:
            app.dependency_overrides.pop(get_video_service, None)

    def test_page_less_than_1_returns_422(self, client):
        response = client.get("/api/videos/?page=0")
        assert response.status_code == 400  # app maps ValidationError → 400

    def test_size_over_100_returns_422(self, client):
        response = client.get("/api/videos/?size=101")
        assert response.status_code == 400  # app maps ValidationError → 400

    def test_default_pagination_values(self, client, app):
        from src.api.dependencies.services import get_video_service

        svc = AsyncMock()
        svc.list_videos = AsyncMock(return_value=([], 0))
        app.dependency_overrides[get_video_service] = lambda: svc
        try:
            response = client.get("/api/videos/")
            body = response.json()
            assert body["page"] == 1
            assert body["size"] == 20
        finally:
            app.dependency_overrides.pop(get_video_service, None)


class TestGetCategoriesEndpoint:
    """GET /api/videos/categories"""

    def test_returns_list_of_strings(self, client, app):
        from src.api.dependencies.services import get_video_service

        svc = AsyncMock()
        svc.list_categories = AsyncMock(return_value=["education", "music", "gaming"])
        app.dependency_overrides[get_video_service] = lambda: svc
        try:
            response = client.get("/api/videos/categories")
            assert response.status_code == 200
            body = response.json()
            assert isinstance(body, list)
            assert "education" in body
            assert "music" in body
        finally:
            app.dependency_overrides.pop(get_video_service, None)

    def test_empty_categories(self, client, app):
        from src.api.dependencies.services import get_video_service

        svc = AsyncMock()
        svc.list_categories = AsyncMock(return_value=[])
        app.dependency_overrides[get_video_service] = lambda: svc
        try:
            response = client.get("/api/videos/categories")
            assert response.status_code == 200
            assert response.json() == []
        finally:
            app.dependency_overrides.pop(get_video_service, None)


class TestGetVideoByIdEndpoint:
    """GET /api/videos/{video_id}"""

    def test_returns_video_playback_details(self, client, app):
        from src.api.dependencies.services import get_video_service

        svc = AsyncMock()
        svc.get_playback = AsyncMock(return_value=_make_playback())
        app.dependency_overrides[get_video_service] = lambda: svc
        try:
            response = client.get(f"/api/videos/{FAKE_VIDEO_ID}")
            assert response.status_code == 200
            body = response.json()
            assert body["name"] == "Test Video"
            assert body["channel_name"] == "TestChannel"
            assert "360p" in body["resolutions"]
            assert "720p" in body["resolutions"]
            assert body["likes_count"] == 10
            assert body["views_count"] == 100
        finally:
            app.dependency_overrides.pop(get_video_service, None)

    def test_video_not_found_returns_404(self, client, app):
        from src.api.dependencies.services import get_video_service
        from src.errors.videos import VideoNotFoundError

        svc = AsyncMock()
        svc.get_playback = AsyncMock(side_effect=VideoNotFoundError())
        app.dependency_overrides[get_video_service] = lambda: svc
        try:
            response = client.get(f"/api/videos/{uuid.uuid4()}")
            assert response.status_code == 404
        finally:
            app.dependency_overrides.pop(get_video_service, None)

    def test_invalid_uuid_returns_422(self, client):
        response = client.get("/api/videos/not-a-valid-uuid")
        assert response.status_code == 400  # app maps ValidationError → 400

    def test_response_has_required_fields(self, client, app):
        from src.api.dependencies.services import get_video_service

        svc = AsyncMock()
        svc.get_playback = AsyncMock(return_value=_make_playback())
        app.dependency_overrides[get_video_service] = lambda: svc
        try:
            body = client.get(f"/api/videos/{FAKE_VIDEO_ID}").json()
            for field in (
                "id",
                "name",
                "privacy",
                "created_at",
                "channel_name",
                "likes_count",
                "dislikes_count",
                "views_count",
            ):
                assert field in body, f"Missing field: {field}"
        finally:
            app.dependency_overrides.pop(get_video_service, None)


class TestGetVideosByCategoryEndpoint:
    """GET /api/videos/categories/{category}"""

    def test_valid_category_returns_200(self, client, app):
        from src.api.dependencies.services import get_video_service

        svc = AsyncMock()
        svc.list_videos = AsyncMock(return_value=([_make_preview()], 1))
        app.dependency_overrides[get_video_service] = lambda: svc
        try:
            response = client.get("/api/videos/categories/education")
            assert response.status_code == 200
            body = response.json()
            assert "items" in body
            assert "total" in body
        finally:
            app.dependency_overrides.pop(get_video_service, None)

    def test_invalid_category_returns_422(self, client):
        response = client.get("/api/videos/categories/not_a_real_category_xyz")
        assert response.status_code == 400  # app maps ValidationError → 400

    def test_all_valid_categories_are_accepted(self, client, app):
        from src.api.dependencies.services import get_video_service

        svc = AsyncMock()
        svc.list_videos = AsyncMock(return_value=([], 0))
        app.dependency_overrides[get_video_service] = lambda: svc
        try:
            for cat in ("education", "gaming", "music", "technology", "sports"):
                r = client.get(f"/api/videos/categories/{cat}")
                assert r.status_code == 200, f"Category '{cat}' unexpectedly rejected"
        finally:
            app.dependency_overrides.pop(get_video_service, None)


class TestReactToVideoEndpoint:
    """POST /api/videos/{video_id}/reactions"""

    def test_like_returns_200_with_counts(self, client, app):
        from src.api.dependencies.services import get_video_service

        svc = AsyncMock()
        svc.react = AsyncMock(return_value={"like": 11, "dislike": 2})
        app.dependency_overrides[get_video_service] = lambda: svc
        try:
            response = client.post(
                f"/api/videos/{FAKE_VIDEO_ID}/reactions",
                json={"reaction_name": "like"},
            )
            assert response.status_code == 200
            body = response.json()
            assert body["target_type"] == "video"
            assert "reactions" in body
            assert "like" in body["reactions"]
        finally:
            app.dependency_overrides.pop(get_video_service, None)

    def test_dislike_returns_200(self, client, app):
        from src.api.dependencies.services import get_video_service

        svc = AsyncMock()
        svc.react = AsyncMock(return_value={"like": 10, "dislike": 3})
        app.dependency_overrides[get_video_service] = lambda: svc
        try:
            response = client.post(
                f"/api/videos/{FAKE_VIDEO_ID}/reactions",
                json={"reaction_name": "dislike"},
            )
            assert response.status_code == 200
        finally:
            app.dependency_overrides.pop(get_video_service, None)

    def test_invalid_reaction_returns_422(self, client):
        response = client.post(
            f"/api/videos/{FAKE_VIDEO_ID}/reactions",
            json={"reaction_name": "love"},  # not in {"like","dislike"}
        )
        assert response.status_code == 400  # app maps ValidationError → 400

    def test_missing_reaction_name_returns_422(self, client):
        response = client.post(f"/api/videos/{FAKE_VIDEO_ID}/reactions", json={})
        assert response.status_code == 400  # app maps ValidationError → 400

    def test_unauthenticated_returns_401(self, client, app):
        from src.infrastructure.auth import current_active_user

        original = app.dependency_overrides.pop(current_active_user, None)
        try:
            response = client.post(
                f"/api/videos/{FAKE_VIDEO_ID}/reactions",
                json={"reaction_name": "like"},
            )
            assert response.status_code == 401
        finally:
            if original is not None:
                app.dependency_overrides[current_active_user] = original


class TestUpdateVideoPrivacyEndpoint:
    """PATCH /api/videos/{video_id}/privacy"""

    def test_owner_updates_to_private(self, client, app):
        from src.api.dependencies.services import get_video_service

        svc = AsyncMock()
        svc.update_privacy = AsyncMock(return_value=("public", "private"))
        app.dependency_overrides[get_video_service] = lambda: svc
        try:
            response = client.patch(
                f"/api/videos/{FAKE_VIDEO_ID}/privacy?updated_privacy=private"
            )
            assert response.status_code == 200
            body = response.json()
            assert body["old_privacy"] == "public"
            assert body["updated_privacy"] == "private"
        finally:
            app.dependency_overrides.pop(get_video_service, None)

    def test_not_owner_returns_403(self, client, app):
        from src.api.dependencies.services import get_video_service
        from src.errors.videos import VideoPrivacyUpdateForbidden

        svc = AsyncMock()
        svc.update_privacy = AsyncMock(side_effect=VideoPrivacyUpdateForbidden())
        app.dependency_overrides[get_video_service] = lambda: svc
        try:
            response = client.patch(
                f"/api/videos/{FAKE_VIDEO_ID}/privacy?updated_privacy=private"
            )
            assert response.status_code == 403
        finally:
            app.dependency_overrides.pop(get_video_service, None)

    def test_video_not_found_returns_404(self, client, app):
        from src.api.dependencies.services import get_video_service
        from src.errors.videos import VideoNotFoundError

        svc = AsyncMock()
        svc.update_privacy = AsyncMock(side_effect=VideoNotFoundError())
        app.dependency_overrides[get_video_service] = lambda: svc
        try:
            response = client.patch(
                f"/api/videos/{FAKE_VIDEO_ID}/privacy?updated_privacy=public"
            )
            assert response.status_code == 404
        finally:
            app.dependency_overrides.pop(get_video_service, None)

    def test_unauthenticated_returns_401(self, client, app):
        from src.infrastructure.auth import current_active_user

        original = app.dependency_overrides.pop(current_active_user, None)
        try:
            response = client.patch(
                f"/api/videos/{FAKE_VIDEO_ID}/privacy?updated_privacy=private"
            )
            assert response.status_code == 401
        finally:
            if original is not None:
                app.dependency_overrides[current_active_user] = original

    def test_invalid_privacy_value_returns_422(self, client):
        response = client.patch(
            f"/api/videos/{FAKE_VIDEO_ID}/privacy?updated_privacy=friends_only"
        )
        assert response.status_code == 400  # app maps ValidationError → 400
