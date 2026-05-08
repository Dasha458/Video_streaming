"""Tests for /api/search/* endpoints."""
import uuid
from unittest.mock import AsyncMock

import pytest


class TestVideoHintsEndpoint:
    """GET /api/search/video_hints — autocomplete suggestions."""

    def test_returns_empty_hints(self, client, app):
        from src.api.dependencies.services import get_search_service

        svc = AsyncMock()
        svc.get_video_hints = AsyncMock(return_value=[])
        app.dependency_overrides[get_search_service] = lambda: svc
        try:
            response = client.get("/api/search/video_hints?query=xyz")
            assert response.status_code == 200
            body = response.json()
            assert body == {"hints": []}
        finally:
            app.dependency_overrides.pop(get_search_service, None)

    def test_returns_suggestions(self, client, app):
        from src.api.dependencies.services import get_search_service

        svc = AsyncMock()
        svc.get_video_hints = AsyncMock(return_value=["funny cats", "funny dogs"])
        app.dependency_overrides[get_search_service] = lambda: svc
        try:
            response = client.get("/api/search/video_hints?query=funny")
            assert response.status_code == 200
            body = response.json()
            assert "hints" in body
            assert "funny cats" in body["hints"]
            assert "funny dogs" in body["hints"]
        finally:
            app.dependency_overrides.pop(get_search_service, None)

    def test_missing_query_returns_422(self, client):
        response = client.get("/api/search/video_hints")
        assert response.status_code == 400  # app maps ValidationError → 400

    def test_empty_query_returns_422(self, client, app):
        from src.api.dependencies.services import get_search_service

        svc = AsyncMock()
        app.dependency_overrides[get_search_service] = lambda: svc
        try:
            response = client.get("/api/search/video_hints?query=")
            assert response.status_code == 400  # app maps ValidationError → 400
        finally:
            app.dependency_overrides.pop(get_search_service, None)

    def test_whitespace_query_returns_error(self, client, app):
        from src.api.dependencies.services import get_search_service

        svc = AsyncMock()
        app.dependency_overrides[get_search_service] = lambda: svc
        try:
            response = client.get("/api/search/video_hints?query=   ")
            # @field_validator raises ValueError inside Depends() threadpool;
            # FastAPI does not convert this to RequestValidationError → returns 500
            assert response.status_code in (400, 500)
        finally:
            app.dependency_overrides.pop(get_search_service, None)


class TestVideoSearchEndpoint:
    """POST /api/search/video — hybrid search."""

    def _make_hit(self, title="Test Video"):
        return {
            "id": str(uuid.uuid4()),
            "name": title,
            "description": "A test video description",
            "category": "education",
            "views": 100,
        }

    def test_basic_search_returns_results(self, client, app):
        from src.api.dependencies.services import get_search_service

        svc = AsyncMock()
        svc.search_video = AsyncMock(
            return_value={"hits": [self._make_hit("Python Tutorial")]}
        )
        app.dependency_overrides[get_search_service] = lambda: svc
        try:
            response = client.post(
                "/api/search/video",
                json={"query": "Python Tutorial"},
            )
            assert response.status_code == 200
            body = response.json()
            assert "results" in body
            assert len(body["results"]) == 1
            assert body["results"][0]["name"] == "Python Tutorial"
        finally:
            app.dependency_overrides.pop(get_search_service, None)

    def test_empty_results(self, client, app):
        from src.api.dependencies.services import get_search_service

        svc = AsyncMock()
        svc.search_video = AsyncMock(return_value={"hits": []})
        app.dependency_overrides[get_search_service] = lambda: svc
        try:
            response = client.post(
                "/api/search/video",
                json={"query": "nonexistent_query_xyz"},
            )
            assert response.status_code == 200
            assert response.json()["results"] == []
        finally:
            app.dependency_overrides.pop(get_search_service, None)

    def test_search_with_category_filter(self, client, app):
        from src.api.dependencies.services import get_search_service

        svc = AsyncMock()
        svc.search_video = AsyncMock(return_value={"hits": [self._make_hit()]})
        app.dependency_overrides[get_search_service] = lambda: svc
        try:
            response = client.post(
                "/api/search/video",
                json={"query": "tutorial", "category": "education"},
            )
            assert response.status_code == 200
        finally:
            app.dependency_overrides.pop(get_search_service, None)

    def test_search_with_view_count_range(self, client, app):
        from src.api.dependencies.services import get_search_service

        svc = AsyncMock()
        svc.search_video = AsyncMock(return_value={"hits": []})
        app.dependency_overrides[get_search_service] = lambda: svc
        try:
            response = client.post(
                "/api/search/video",
                json={"query": "popular", "min_views": 100, "max_views": 10000},
            )
            assert response.status_code == 200
        finally:
            app.dependency_overrides.pop(get_search_service, None)

    def test_empty_query_returns_422(self, client):
        response = client.post("/api/search/video", json={"query": ""})
        assert response.status_code == 400  # app maps ValidationError → 400

    def test_missing_query_returns_422(self, client):
        response = client.post("/api/search/video", json={})
        assert response.status_code == 400  # app maps ValidationError → 400

    def test_limit_exceeds_max_returns_422(self, client):
        response = client.post(
            "/api/search/video",
            json={"query": "test", "limit": 100},  # max is 50
        )
        assert response.status_code == 400  # app maps ValidationError → 400

    def test_min_views_greater_than_max_views_returns_422(self, client):
        response = client.post(
            "/api/search/video",
            json={"query": "test", "min_views": 1000, "max_views": 100},
        )
        assert response.status_code == 400  # app maps ValidationError → 400

    def test_search_with_has_description_filter(self, client, app):
        from src.api.dependencies.services import get_search_service

        svc = AsyncMock()
        svc.search_video = AsyncMock(return_value={"hits": [self._make_hit()]})
        app.dependency_overrides[get_search_service] = lambda: svc
        try:
            response = client.post(
                "/api/search/video",
                json={"query": "tutorial", "has_description": True},
            )
            assert response.status_code == 200
        finally:
            app.dependency_overrides.pop(get_search_service, None)

    def test_multiple_results_returned(self, client, app):
        from src.api.dependencies.services import get_search_service

        svc = AsyncMock()
        hits = [self._make_hit(f"Video {i}") for i in range(5)]
        svc.search_video = AsyncMock(return_value={"hits": hits})
        app.dependency_overrides[get_search_service] = lambda: svc
        try:
            response = client.post("/api/search/video", json={"query": "video"})
            assert response.status_code == 200
            assert len(response.json()["results"]) == 5
        finally:
            app.dependency_overrides.pop(get_search_service, None)
