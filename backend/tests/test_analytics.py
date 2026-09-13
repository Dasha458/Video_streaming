"""Tests for /api/analytics/* endpoints."""
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from tests.conftest import TEST_USER_ID


def _delta(value: int, previous: int = 0):
    from src.schemas.analytics import DeltaInt

    return DeltaInt(value=value, previous=previous, delta_percent=0.0)


def _make_overview():
    from src.schemas.analytics import OverviewResponse

    return OverviewResponse(
        period="28d",
        total_views=_delta(1000),
        total_subscribers=50,
        total_likes=_delta(200),
        total_comments=_delta(30),
        total_watch_time_seconds=_delta(0),
        views_per_day=[{"date": "2025-01-01", "count": 100}],
        top_videos=[],
    )


def _make_content():
    from src.schemas.analytics import ContentResponse

    return ContentResponse(period="28d", videos=[])


def _make_audience():
    from src.schemas.analytics import AudienceResponse

    return AudienceResponse(
        period="28d",
        subscribers_per_day=[],
        unique_viewers=100,
        returning_viewers=40,
        comments_per_day=[],
    )


def _channel_mock():
    ch = MagicMock()
    ch.id = uuid.uuid4()
    ch.name = "TestChannel"
    ch.user_id = TEST_USER_ID
    return ch


class TestAnalyticsOverviewEndpoint:
    """GET /api/analytics/overview — requires auth + channel."""

    def test_returns_200_with_overview_data(self, client, app):
        from src.api.dependencies.services import get_service_and_channel

        svc = AsyncMock()
        svc.get_overview = AsyncMock(return_value=_make_overview())
        ch = _channel_mock()
        app.dependency_overrides[get_service_and_channel] = lambda: (svc, ch)
        try:
            response = client.get("/api/analytics/overview")
            assert response.status_code == 200
            body = response.json()
            assert "total_views" in body
            assert "total_subscribers" in body
            assert "total_likes" in body
            assert "total_comments" in body
            assert "views_per_day" in body
            assert body["total_views"]["value"] == 1000
            assert body["total_subscribers"] == 50
        finally:
            app.dependency_overrides.pop(get_service_and_channel, None)

    def test_unauthenticated_returns_401(self, client, app):
        from src.infrastructure.auth import current_active_user

        original = app.dependency_overrides.pop(current_active_user, None)
        try:
            response = client.get("/api/analytics/overview")
            assert response.status_code == 401
        finally:
            if original is not None:
                app.dependency_overrides[current_active_user] = original

    def test_no_channel_returns_404(self, client, app):
        from src.api.dependencies.services import get_service_and_channel
        from src.errors.files import ChannelNotFoundError
        from fastapi import HTTPException

        async def raise_404():
            raise HTTPException(status_code=404, detail="Channel not found")

        app.dependency_overrides[get_service_and_channel] = raise_404
        try:
            response = client.get("/api/analytics/overview")
            assert response.status_code == 404
        finally:
            app.dependency_overrides.pop(get_service_and_channel, None)


class TestAnalyticsContentEndpoint:
    """GET /api/analytics/content — requires auth + channel."""

    def test_returns_200_with_content_data(self, client, app):
        from src.api.dependencies.services import get_service_and_channel

        svc = AsyncMock()
        svc.get_content = AsyncMock(return_value=_make_content())
        ch = _channel_mock()
        app.dependency_overrides[get_service_and_channel] = lambda: (svc, ch)
        try:
            response = client.get("/api/analytics/content")
            assert response.status_code == 200
            body = response.json()
            assert "videos" in body
            assert isinstance(body["videos"], list)
        finally:
            app.dependency_overrides.pop(get_service_and_channel, None)

    def test_unauthenticated_returns_401(self, client, app):
        from src.infrastructure.auth import current_active_user

        original = app.dependency_overrides.pop(current_active_user, None)
        try:
            response = client.get("/api/analytics/content")
            assert response.status_code == 401
        finally:
            if original is not None:
                app.dependency_overrides[current_active_user] = original


class TestAnalyticsAudienceEndpoint:
    """GET /api/analytics/audience — requires auth + channel."""

    def test_returns_200_with_audience_data(self, client, app):
        from src.api.dependencies.services import get_service_and_channel

        svc = AsyncMock()
        svc.get_audience = AsyncMock(return_value=_make_audience())
        ch = _channel_mock()
        app.dependency_overrides[get_service_and_channel] = lambda: (svc, ch)
        try:
            response = client.get("/api/analytics/audience")
            assert response.status_code == 200
            body = response.json()
            assert "unique_viewers" in body
            assert "returning_viewers" in body
            assert "subscribers_per_day" in body
            assert body["unique_viewers"] == 100
            assert body["returning_viewers"] == 40
        finally:
            app.dependency_overrides.pop(get_service_and_channel, None)

    def test_unauthenticated_returns_401(self, client, app):
        from src.infrastructure.auth import current_active_user

        original = app.dependency_overrides.pop(current_active_user, None)
        try:
            response = client.get("/api/analytics/audience")
            assert response.status_code == 401
        finally:
            if original is not None:
                app.dependency_overrides[current_active_user] = original
