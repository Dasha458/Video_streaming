"""Tests for /api/files/* endpoints."""

import uuid
from unittest.mock import AsyncMock, MagicMock

FAKE_VIDEO_ID = uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")
FAKE_UPLOAD_ID = uuid.UUID("dddddddd-dddd-dddd-dddd-dddddddddddd")


class TestResumableUpload:
    """/api/files/uploads/* -- the video arrives in parts.

    The single-shot POST /api/files/videos these tests used to exercise
    is gone. A 500 MB body in one request fails entirely on any dropped
    connection, and forced the gateway to accept a body that size from
    anyone who asked.
    """

    def _start(self, client, size=50_000_000, content_type="video/mp4"):
        return client.post(
            "/api/files/uploads",
            json={"filename": "clip.mp4", "content_type": content_type, "size": size},
        )

    def _status(self, parts=(1,), received=10_000_000):
        from src.schemas.uploads import UploadSessionStatus

        return UploadSessionStatus(
            upload_id=FAKE_UPLOAD_ID,
            part_size=10_485_760,
            declared_size=50_000_000,
            received_parts=list(parts),
            received_bytes=received,
        )

    def _override(self, app, svc):
        from src.api.dependencies.services import get_upload_service

        app.dependency_overrides[get_upload_service] = lambda: svc
        return get_upload_service

    def test_starting_returns_the_part_size_to_use(self, client, app):
        from src.schemas.uploads import UploadStarted

        svc = AsyncMock()
        svc.start = AsyncMock(
            return_value=UploadStarted(
                upload_id=FAKE_UPLOAD_ID, part_size=10_485_760, total_parts=5
            )
        )
        key = self._override(app, svc)
        try:
            response = self._start(client)
            assert response.status_code == 200
            body = response.json()
            assert body["upload_id"] == str(FAKE_UPLOAD_ID)
            assert body["part_size"] == 10_485_760
            assert body["total_parts"] == 5
        finally:
            app.dependency_overrides.pop(key, None)

    def test_starting_without_auth_returns_401(self, client, app):
        from src.infrastructure.auth import current_active_user

        original = app.dependency_overrides.pop(current_active_user, None)
        try:
            response = client.post(
                "/api/files/uploads",
                json={
                    "filename": "clip.mp4",
                    "content_type": "video/mp4",
                    "size": 1000,
                },
            )
            assert response.status_code == 401
        finally:
            if original is not None:
                app.dependency_overrides[current_active_user] = original

    def test_a_part_reports_everything_stored_so_far(self, client, app):
        """So an interrupted client can see what it still owes without a
        separate request."""
        svc = AsyncMock()
        svc.upload_part = AsyncMock(return_value=self._status(parts=(1, 2)))
        key = self._override(app, svc)
        try:
            response = client.put(
                f"/api/files/uploads/{FAKE_UPLOAD_ID}/parts/2",
                content=b"x" * 1024,
            )
            assert response.status_code == 200
            assert response.json()["received_parts"] == [1, 2]
        finally:
            app.dependency_overrides.pop(key, None)

    def test_part_numbers_start_at_one(self, client, app):
        svc = AsyncMock()
        key = self._override(app, svc)
        try:
            response = client.put(
                f"/api/files/uploads/{FAKE_UPLOAD_ID}/parts/0", content=b"x"
            )
            # 400, not 422: this application answers every validation
            # failure with its own VALIDATION_ERROR envelope.
            assert response.status_code == 400
            svc.upload_part.assert_not_called()
        finally:
            app.dependency_overrides.pop(key, None)

    def test_asking_what_arrived_is_how_a_resume_starts(self, client, app):
        svc = AsyncMock()
        svc.status = AsyncMock(return_value=self._status(parts=(1, 2, 3)))
        key = self._override(app, svc)
        try:
            response = client.get(f"/api/files/uploads/{FAKE_UPLOAD_ID}")
            assert response.status_code == 200
            assert response.json()["received_parts"] == [1, 2, 3]
        finally:
            app.dependency_overrides.pop(key, None)

    def test_completing_creates_the_video(self, client, app):
        from src.schemas.endpoint import FileMeta, FileResponse

        svc = AsyncMock()
        svc.complete = AsyncMock(
            return_value=FileResponse(
                status="accepted",
                files=[
                    FileMeta(file_id=FAKE_VIDEO_ID, filename="Test Video", size=1000)
                ],
            )
        )
        key = self._override(app, svc)
        try:
            response = client.post(
                f"/api/files/uploads/{FAKE_UPLOAD_ID}/complete",
                data={
                    "name": "Test Video",
                    "description": "A test video",
                    "category": "education",
                    "privacy": "public",
                },
            )
            assert response.status_code == 200
            assert response.json()["status"] == "accepted"
        finally:
            app.dependency_overrides.pop(key, None)

    def test_completing_without_a_name_is_refused(self, client, app):
        svc = AsyncMock()
        key = self._override(app, svc)
        try:
            response = client.post(
                f"/api/files/uploads/{FAKE_UPLOAD_ID}/complete",
                data={"name": "   ", "category": "education", "privacy": "public"},
            )
            assert response.status_code == 400
            svc.complete.assert_not_called()
        finally:
            app.dependency_overrides.pop(key, None)

    def test_completing_an_invalid_category_is_refused(self, client, app):
        svc = AsyncMock()
        key = self._override(app, svc)
        try:
            response = client.post(
                f"/api/files/uploads/{FAKE_UPLOAD_ID}/complete",
                data={
                    "name": "Test Video",
                    "category": "not-a-category",
                    "privacy": "public",
                },
            )
            assert response.status_code == 400
            svc.complete.assert_not_called()
        finally:
            app.dependency_overrides.pop(key, None)

    def test_completing_a_file_already_on_the_platform_returns_409(self, client, app):
        from src.errors.files import DuplicateVideoError

        svc = AsyncMock()
        svc.complete = AsyncMock(side_effect=DuplicateVideoError())
        key = self._override(app, svc)
        try:
            response = client.post(
                f"/api/files/uploads/{FAKE_UPLOAD_ID}/complete",
                data={
                    "name": "Test Video",
                    "category": "education",
                    "privacy": "public",
                },
            )
            assert response.status_code == 409
        finally:
            app.dependency_overrides.pop(key, None)

    def test_giving_up_releases_the_parts(self, client, app):
        """An abandoned multipart upload holds every part already sent and
        appears in no object listing."""
        svc = AsyncMock()
        svc.abort = AsyncMock(return_value=None)
        key = self._override(app, svc)
        try:
            response = client.delete(f"/api/files/uploads/{FAKE_UPLOAD_ID}")
            assert response.status_code == 204
            svc.abort.assert_awaited_once()
        finally:
            app.dependency_overrides.pop(key, None)


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
