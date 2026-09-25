"""Tests for /api/files/* endpoints."""

import io
import uuid
from unittest.mock import AsyncMock, MagicMock

FAKE_VIDEO_ID = uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")


class TestUploadVideoEndpoint:
    """POST /api/files/videos — multipart/form-data upload."""

    def _upload(
        self,
        client,
        name="Test Video",
        description="A test video",
        category="education",
        privacy="public",
    ):
        # Metadata travels in the multipart body, not the query string --
        # titles and descriptions would otherwise land in access logs.
        return client.post(
            "/api/files/videos",
            data={
                "name": name,
                "description": description,
                "category": category,
                "privacy": privacy,
            },
            files={
                "video": ("test.mp4", io.BytesIO(b"fake video content"), "video/mp4"),
                "thumbnail": ("thumb.jpg", io.BytesIO(b"fake image"), "image/jpeg"),
            },
        )

    def test_upload_returns_accepted(self, client, app):
        from src.api.dependencies.services import get_file_service

        svc = AsyncMock()
        svc.upload_video = AsyncMock(
            return_value=MagicMock(
                status="accepted",
                files=[
                    MagicMock(
                        file_id=FAKE_VIDEO_ID,
                        filename="test.mp4",
                        size=1000,
                    )
                ],
            )
        )
        # Make the return value JSON-serializable
        from src.schemas.endpoint import FileMeta, FileResponse

        svc.upload_video = AsyncMock(
            return_value=FileResponse(
                status="accepted",
                files=[FileMeta(file_id=FAKE_VIDEO_ID, filename="test.mp4", size=1000)],
            )
        )
        app.dependency_overrides[get_file_service] = lambda: svc
        try:
            response = self._upload(client)
            assert response.status_code == 200
            body = response.json()
            assert body["status"] == "accepted"
            assert len(body["files"]) == 1
            assert body["files"][0]["filename"] == "test.mp4"
        finally:
            app.dependency_overrides.pop(get_file_service, None)

    def test_upload_without_thumbnail_is_accepted(self, client, app):
        """The UI marks only Title required; a thumbnail-less upload must work."""
        from src.api.dependencies.services import get_file_service
        from src.schemas.endpoint import FileMeta, FileResponse

        svc = AsyncMock()
        svc.upload_video = AsyncMock(
            return_value=FileResponse(
                status="accepted",
                files=[FileMeta(file_id=FAKE_VIDEO_ID, filename="test.mp4", size=1000)],
            )
        )
        app.dependency_overrides[get_file_service] = lambda: svc
        try:
            response = client.post(
                "/api/files/videos",
                data={
                    "name": "No thumbnail",
                    "description": "",
                    "category": "education",
                    "privacy": "public",
                },
                files={
                    "video": ("test.mp4", io.BytesIO(b"fake"), "video/mp4"),
                },
            )
            assert response.status_code == 200
            assert svc.upload_video.await_args.kwargs["thumbnail"] is None
        finally:
            app.dependency_overrides.pop(get_file_service, None)

    def test_upload_with_empty_description_is_accepted(self, client, app):
        """Description is optional in the UI, so an empty one must not 400."""
        from src.api.dependencies.services import get_file_service
        from src.schemas.endpoint import FileMeta, FileResponse

        svc = AsyncMock()
        svc.upload_video = AsyncMock(
            return_value=FileResponse(
                status="accepted",
                files=[FileMeta(file_id=FAKE_VIDEO_ID, filename="test.mp4", size=1000)],
            )
        )
        app.dependency_overrides[get_file_service] = lambda: svc
        try:
            response = self._upload(client, description="")
            assert response.status_code == 200
            assert svc.upload_video.await_args.kwargs["description"] == ""
        finally:
            app.dependency_overrides.pop(get_file_service, None)

    def test_upload_without_auth_returns_401(self, client, app):
        from src.infrastructure.auth import current_active_user

        original = app.dependency_overrides.pop(current_active_user, None)
        try:
            response = self._upload(client)
            assert response.status_code == 401
        finally:
            if original is not None:
                app.dependency_overrides[current_active_user] = original

    def test_upload_missing_video_file_returns_422(self, client):
        response = client.post(
            "/api/files/videos",
            data={
                "name": "Test Video",
                "description": "A test video",
                "category": "education",
                "privacy": "public",
            },
            files={
                "thumbnail": ("thumb.jpg", io.BytesIO(b"fake image"), "image/jpeg"),
            },
        )
        assert response.status_code == 400  # app maps ValidationError → 400

    def test_upload_empty_name_returns_422(self, client, app):
        from src.api.dependencies.services import get_file_service

        svc = AsyncMock()
        app.dependency_overrides[get_file_service] = lambda: svc
        try:
            response = self._upload(client, name="   ")
            assert response.status_code == 400  # app maps ValidationError → 400
        finally:
            app.dependency_overrides.pop(get_file_service, None)

    def test_upload_invalid_category_returns_422(self, client):
        response = self._upload(client, category="not_a_real_category")
        assert response.status_code == 400  # app maps ValidationError → 400

    def test_upload_duplicate_video_returns_409(self, client, app):
        from src.api.dependencies.services import get_file_service
        from src.errors.files import DuplicateVideoError

        svc = AsyncMock()
        svc.upload_video = AsyncMock(side_effect=DuplicateVideoError())
        app.dependency_overrides[get_file_service] = lambda: svc
        try:
            response = self._upload(client)
            assert response.status_code == 409
        finally:
            app.dependency_overrides.pop(get_file_service, None)


class TestDeleteVideoEndpoint:
    """DELETE /api/files/videos/{video_id}"""

    def test_owner_deletes_video_returns_200(self, client, app):
        from src.api.dependencies.services import get_file_service

        deleted_video = MagicMock()
        deleted_video.name = "Test Video"
        deleted_video.size = 5000

        svc = AsyncMock()
        svc.delete_video = AsyncMock(return_value=deleted_video)
        app.dependency_overrides[get_file_service] = lambda: svc
        try:
            response = client.delete(f"/api/files/videos/{FAKE_VIDEO_ID}")
            assert response.status_code == 200
            body = response.json()
            assert body["status"] == "deleted"
            assert len(body["files"]) == 1
        finally:
            app.dependency_overrides.pop(get_file_service, None)

    def test_delete_without_auth_returns_401(self, client, app):
        from src.infrastructure.auth import current_active_user

        original = app.dependency_overrides.pop(current_active_user, None)
        try:
            response = client.delete(f"/api/files/videos/{FAKE_VIDEO_ID}")
            assert response.status_code == 401
        finally:
            if original is not None:
                app.dependency_overrides[current_active_user] = original

    def test_delete_nonexistent_video_returns_404(self, client, app):
        from src.api.dependencies.services import get_file_service
        from src.errors.videos import VideoNotFoundError

        svc = AsyncMock()
        svc.delete_video = AsyncMock(side_effect=VideoNotFoundError())
        app.dependency_overrides[get_file_service] = lambda: svc
        try:
            response = client.delete(f"/api/files/videos/{uuid.uuid4()}")
            assert response.status_code == 404
        finally:
            app.dependency_overrides.pop(get_file_service, None)

    def test_delete_invalid_uuid_returns_422(self, client):
        response = client.delete("/api/files/videos/not-a-uuid")
        assert response.status_code == 400  # app maps ValidationError → 400


class TestSignUrlEndpoint:
    """GET /api/files/sign_url"""

    def test_returns_signed_url(self, client, app):
        from src.api.dependencies.services import get_file_signing_service

        svc = AsyncMock()
        svc.create_signed_url = AsyncMock(
            return_value={
                "path": "videos/master.m3u8",
                "signed_url": "http://localhost:9000/videos/master.m3u8?sig=abc",
                "expires_in": 300,
            }
        )
        app.dependency_overrides[get_file_signing_service] = lambda: svc
        try:
            response = client.get("/api/files/sign_url?file_path=videos/master.m3u8")
            assert response.status_code == 200
            body = response.json()
            assert "signed_url" in body
            assert "path" in body
            assert "expires_in" in body
        finally:
            app.dependency_overrides.pop(get_file_signing_service, None)

    def test_missing_file_path_returns_422(self, client):
        response = client.get("/api/files/sign_url")
        assert response.status_code == 400  # app maps ValidationError → 400

    def test_file_not_found_returns_404(self, client, app):
        from src.api.dependencies.services import get_file_signing_service
        from src.errors.files import FileNotFoundS3Error

        svc = AsyncMock()
        svc.create_signed_url = AsyncMock(side_effect=FileNotFoundS3Error())
        app.dependency_overrides[get_file_signing_service] = lambda: svc
        try:
            response = client.get("/api/files/sign_url?file_path=nonexistent.mp4")
            assert response.status_code == 404
        finally:
            app.dependency_overrides.pop(get_file_signing_service, None)

    def test_response_contains_signed_url_header(self, client, app):
        from src.api.dependencies.services import get_file_signing_service

        svc = AsyncMock()
        svc.create_signed_url = AsyncMock(
            return_value={
                "path": "videos/master.m3u8",
                "signed_url": "http://localhost:9000/sig=abc",
                "expires_in": 300,
            }
        )
        app.dependency_overrides[get_file_signing_service] = lambda: svc
        try:
            response = client.get("/api/files/sign_url?file_path=videos/master.m3u8")
            assert "X-Signed-Url" in response.headers
        finally:
            app.dependency_overrides.pop(get_file_signing_service, None)
