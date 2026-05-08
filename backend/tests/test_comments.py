"""Tests for /api/comments/* endpoints."""
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from tests.conftest import TEST_USER_ID

FAKE_VIDEO_ID = uuid.UUID("dddddddd-dddd-dddd-dddd-dddddddddddd")
FAKE_COMMENT_ID = uuid.UUID("eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee")


def _make_comment_read(comment_id=FAKE_COMMENT_ID):
    from src.schemas.comments import CommentRead

    return CommentRead(
        id=comment_id,
        user_id=TEST_USER_ID,
        content="This is a test comment",
        created_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
        likes_count=3,
        dislikes_count=0,
        parent_id=None,
        user_name="testuser",
        user_avatar=None,
        replies=[],
    )


class TestListCommentsEndpoint:
    """GET /api/comments/{video_id}"""

    def test_returns_empty_list(self, client, app):
        from src.api.dependencies.services import get_comment_service

        svc = AsyncMock()
        svc.get_by_video = AsyncMock(return_value=([], 0))
        app.dependency_overrides[get_comment_service] = lambda: svc
        try:
            response = client.get(f"/api/comments/{FAKE_VIDEO_ID}")
            assert response.status_code == 200
            body = response.json()
            assert body["items"] == []
            assert body["total"] == 0
        finally:
            app.dependency_overrides.pop(get_comment_service, None)

    def test_returns_comment_list(self, client, app):
        from src.api.dependencies.services import get_comment_service

        svc = AsyncMock()
        svc.get_by_video = AsyncMock(return_value=([_make_comment_read()], 1))
        app.dependency_overrides[get_comment_service] = lambda: svc
        try:
            response = client.get(f"/api/comments/{FAKE_VIDEO_ID}")
            assert response.status_code == 200
            body = response.json()
            assert len(body["items"]) == 1
            assert body["items"][0]["content"] == "This is a test comment"
            assert body["items"][0]["user_name"] == "testuser"
            assert body["total"] == 1
        finally:
            app.dependency_overrides.pop(get_comment_service, None)

    def test_invalid_video_uuid_returns_422(self, client):
        response = client.get("/api/comments/not-a-uuid")
        assert response.status_code == 400  # app maps ValidationError → 400

    def test_pagination_query_works(self, client, app):
        from src.api.dependencies.services import get_comment_service

        svc = AsyncMock()
        svc.get_by_video = AsyncMock(return_value=([], 0))
        app.dependency_overrides[get_comment_service] = lambda: svc
        try:
            response = client.get(f"/api/comments/{FAKE_VIDEO_ID}?page=2&size=10")
            assert response.status_code == 200
            body = response.json()
            assert body["page"] == 2
            assert body["size"] == 10
        finally:
            app.dependency_overrides.pop(get_comment_service, None)

    def test_invalid_page_returns_422(self, client):
        response = client.get(f"/api/comments/{FAKE_VIDEO_ID}?page=0")
        assert response.status_code == 400  # app maps ValidationError → 400


class TestCreateCommentEndpoint:
    """POST /api/comments/{video_id}"""

    def test_create_comment_returns_201(self, client, app):
        from src.api.dependencies.services import get_comment_service

        svc = AsyncMock()
        svc.create = AsyncMock(return_value=_make_comment_read())
        app.dependency_overrides[get_comment_service] = lambda: svc
        try:
            response = client.post(
                f"/api/comments/{FAKE_VIDEO_ID}",
                json={"content": "Great video!"},
            )
            assert response.status_code == 201
            body = response.json()
            assert body["content"] == "This is a test comment"
            assert body["user_name"] == "testuser"
        finally:
            app.dependency_overrides.pop(get_comment_service, None)

    def test_create_reply_comment(self, client, app):
        from src.api.dependencies.services import get_comment_service

        svc = AsyncMock()
        reply = _make_comment_read()
        reply.parent_id = FAKE_COMMENT_ID
        svc.create = AsyncMock(return_value=reply)
        app.dependency_overrides[get_comment_service] = lambda: svc
        try:
            response = client.post(
                f"/api/comments/{FAKE_VIDEO_ID}",
                json={"content": "Reply!", "parent_id": str(FAKE_COMMENT_ID)},
            )
            assert response.status_code == 201
        finally:
            app.dependency_overrides.pop(get_comment_service, None)

    def test_empty_content_returns_422(self, client, app):
        from src.api.dependencies.services import get_comment_service

        svc = AsyncMock()
        app.dependency_overrides[get_comment_service] = lambda: svc
        try:
            response = client.post(
                f"/api/comments/{FAKE_VIDEO_ID}",
                json={"content": ""},
            )
            assert response.status_code == 400  # app maps ValidationError → 400
        finally:
            app.dependency_overrides.pop(get_comment_service, None)

    def test_whitespace_only_content_returns_422(self, client, app):
        from src.api.dependencies.services import get_comment_service

        svc = AsyncMock()
        app.dependency_overrides[get_comment_service] = lambda: svc
        try:
            response = client.post(
                f"/api/comments/{FAKE_VIDEO_ID}",
                json={"content": "   "},
            )
            assert response.status_code == 400  # app maps ValidationError → 400
        finally:
            app.dependency_overrides.pop(get_comment_service, None)

    def test_missing_content_returns_422(self, client):
        response = client.post(f"/api/comments/{FAKE_VIDEO_ID}", json={})
        assert response.status_code == 400  # app maps ValidationError → 400

    def test_unauthenticated_returns_401(self, client, app):
        from src.infrastructure.auth import current_active_user

        original = app.dependency_overrides.pop(current_active_user, None)
        try:
            response = client.post(
                f"/api/comments/{FAKE_VIDEO_ID}",
                json={"content": "Hello"},
            )
            assert response.status_code == 401
        finally:
            if original is not None:
                app.dependency_overrides[current_active_user] = original


class TestReactToCommentEndpoint:
    """POST /api/comments/{comment_id}/reaction"""

    def test_like_comment_returns_200(self, client, app):
        from src.api.dependencies.services import get_comment_service

        svc = AsyncMock()
        svc.react = AsyncMock(return_value={"like": 4, "dislike": 0})
        app.dependency_overrides[get_comment_service] = lambda: svc
        try:
            response = client.post(
                f"/api/comments/{FAKE_COMMENT_ID}/reaction",
                json={"reaction_name": "like"},
            )
            assert response.status_code == 200
            body = response.json()
            assert body["target_type"] == "comment"
            assert "reactions" in body
            assert body["reactions"]["like"] == 4
        finally:
            app.dependency_overrides.pop(get_comment_service, None)

    def test_invalid_reaction_returns_422(self, client):
        response = client.post(
            f"/api/comments/{FAKE_COMMENT_ID}/reaction",
            json={"reaction_name": "love"},
        )
        assert response.status_code == 400  # app maps ValidationError → 400

    def test_unauthenticated_returns_401(self, client, app):
        from src.infrastructure.auth import current_active_user

        original = app.dependency_overrides.pop(current_active_user, None)
        try:
            response = client.post(
                f"/api/comments/{FAKE_COMMENT_ID}/reaction",
                json={"reaction_name": "like"},
            )
            assert response.status_code == 401
        finally:
            if original is not None:
                app.dependency_overrides[current_active_user] = original


class TestDeleteCommentEndpoint:
    """DELETE /api/comments/{comment_id}"""

    def test_author_deletes_returns_204(self, client, app):
        from src.api.dependencies.services import get_comment_service

        svc = AsyncMock()
        svc.delete = AsyncMock(return_value=None)
        app.dependency_overrides[get_comment_service] = lambda: svc
        try:
            response = client.delete(f"/api/comments/{FAKE_COMMENT_ID}")
            assert response.status_code == 204
        finally:
            app.dependency_overrides.pop(get_comment_service, None)

    def test_not_author_returns_403(self, client, app):
        from src.api.dependencies.services import get_comment_service
        from src.errors.comments import CommentDeleteForbiddenError

        svc = AsyncMock()
        svc.delete = AsyncMock(side_effect=CommentDeleteForbiddenError())
        app.dependency_overrides[get_comment_service] = lambda: svc
        try:
            response = client.delete(f"/api/comments/{FAKE_COMMENT_ID}")
            assert response.status_code == 403
        finally:
            app.dependency_overrides.pop(get_comment_service, None)

    def test_comment_not_found_returns_404(self, client, app):
        from src.api.dependencies.services import get_comment_service
        from src.errors.comments import CommentNotFoundError

        svc = AsyncMock()
        svc.delete = AsyncMock(side_effect=CommentNotFoundError())
        app.dependency_overrides[get_comment_service] = lambda: svc
        try:
            response = client.delete(f"/api/comments/{uuid.uuid4()}")
            assert response.status_code == 404
        finally:
            app.dependency_overrides.pop(get_comment_service, None)

    def test_unauthenticated_returns_401(self, client, app):
        from src.infrastructure.auth import current_active_user

        original = app.dependency_overrides.pop(current_active_user, None)
        try:
            response = client.delete(f"/api/comments/{FAKE_COMMENT_ID}")
            assert response.status_code == 401
        finally:
            if original is not None:
                app.dependency_overrides[current_active_user] = original

    def test_invalid_uuid_returns_422(self, client):
        response = client.delete("/api/comments/not-a-uuid")
        assert response.status_code == 400  # app maps ValidationError → 400
