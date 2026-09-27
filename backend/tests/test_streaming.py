"""
GET /api/videos/{id}/stream-url and the gateway's media authoriser.

These replace the tests for GET /api/files/sign_url, an endpoint that
signed any path it was given without asking who wanted it.
"""

import uuid
from unittest.mock import AsyncMock

import pytest

from src.errors.files import MediaAccessDeniedError
from src.errors.videos import VideoNotFoundError
from src.services.streaming import StreamService


class TestStreamUrlEndpoint:
    """GET /api/videos/{video_id}/stream-url"""

    @staticmethod
    def _service(url="/minio/videos/abc/master.m3u8", expires=3600):
        svc = AsyncMock(spec=StreamService)
        svc.stream_url = AsyncMock(return_value=(url, expires))
        return svc

    def test_returns_the_url_and_its_lifetime(self, client, app):
        from src.api.dependencies.services import get_stream_service

        svc = self._service()
        app.dependency_overrides[get_stream_service] = lambda: svc
        try:
            video_id = uuid.uuid4()
            response = client.get(f"/api/videos/{video_id}/stream-url")
            assert response.status_code == 200
            assert response.json() == {
                "url": "/minio/videos/abc/master.m3u8",
                "expires_in": 3600,
            }
            assert svc.stream_url.await_args.args[0] == video_id
        finally:
            app.dependency_overrides.pop(get_stream_service, None)

    def test_redirects_when_asked_to(self, client, app):
        from src.api.dependencies.services import get_stream_service

        app.dependency_overrides[get_stream_service] = lambda: self._service()
        try:
            response = client.get(
                f"/api/videos/{uuid.uuid4()}/stream-url?redirect=true",
                follow_redirects=False,
            )
            assert response.status_code == 302
            assert response.headers["location"] == "/minio/videos/abc/master.m3u8"
        finally:
            app.dependency_overrides.pop(get_stream_service, None)

    def test_a_video_the_caller_cannot_watch_is_a_404(self, client, app):
        from src.api.dependencies.services import get_stream_service

        svc = AsyncMock(spec=StreamService)
        svc.stream_url = AsyncMock(side_effect=VideoNotFoundError())
        app.dependency_overrides[get_stream_service] = lambda: svc
        try:
            response = client.get(f"/api/videos/{uuid.uuid4()}/stream-url")
            assert response.status_code == 404
        finally:
            app.dependency_overrides.pop(get_stream_service, None)


class TestMediaAuthorisation:
    """The gateway subrequest that used to be GET /api/files/sign_url."""

    def test_signs_a_path_the_caller_may_watch(self, client, app):
        from src.api.dependencies.services import get_stream_service

        svc = AsyncMock(spec=StreamService)
        svc.authorize_media = AsyncMock(
            return_value={
                "path": "videos/abc/seg1.ts",
                "signed_url": "http://minio:9000/videos/abc/seg1.ts?sig=x",
                "expires_in": 3600,
            }
        )
        app.dependency_overrides[get_stream_service] = lambda: svc
        try:
            response = client.get(
                "/api/videos/stream-authorize",
                params={"file_path": "/minio/videos/abc/seg1.ts"},
            )
            assert response.status_code == 200
            # The gateway reads the URL off this header, not the body.
            assert response.headers["X-Signed-Url"].startswith("http://minio:9000/")
        finally:
            app.dependency_overrides.pop(get_stream_service, None)

    def test_refuses_a_path_for_a_video_the_caller_cannot_watch(self, client, app):
        from src.api.dependencies.services import get_stream_service

        svc = AsyncMock(spec=StreamService)
        svc.authorize_media = AsyncMock(side_effect=MediaAccessDeniedError())
        app.dependency_overrides[get_stream_service] = lambda: svc
        try:
            response = client.get(
                "/api/videos/stream-authorize",
                params={"file_path": "/minio/videos/private-one/seg1.ts"},
            )
            # 403, not 404: the gateway treats anything else as an internal
            # error and shows the viewer a 500.
            assert response.status_code == 403
            assert "X-Signed-Url" not in response.headers
        finally:
            app.dependency_overrides.pop(get_stream_service, None)

    def test_the_old_backdoor_is_gone(self, client):
        """Signing an arbitrary path is no longer something the API offers."""
        response = client.get(
            "/api/files/sign_url", params={"file_path": "/minio/videos/x/master.m3u8"}
        )
        assert response.status_code == 404


class TestStreamServiceRules:
    """StreamService.authorize_media's own path handling."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "path",
        [
            "/minio/videos",  # no object
            "/minio/videos/abc",  # the video folder itself, no object
            "/etc/passwd",  # not a gateway path at all
            "/minio/other-bucket/secrets/key.pem",  # not under videos/
            "/minio/videos/not-a-uuid/master.m3u8",  # id that cannot be looked up
        ],
    )
    async def test_a_path_that_names_no_video_is_refused(self, path):
        signer = AsyncMock()
        service = StreamService(AsyncMock(), signer)

        with pytest.raises(MediaAccessDeniedError):
            await service.authorize_media(path, user_id=None)

        signer.create_signed_url.assert_not_awaited()
