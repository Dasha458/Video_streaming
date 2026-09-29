"""
The backend's object storage client.

It had no tests, and it swallowed every storage error it met: a failed
upload looked like success to the caller, a missing object streamed back
as an empty 200, and a failed delete let a rollback that exists for it
never run. The same defect lived in the convertor's copy of this client.
"""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from botocore.exceptions import ClientError

from src.errors.files import (
    FileNotFoundS3Error,
    S3DeletionError,
    S3DownloadError,
    VideoUploadFailedError,
)
from src.infrastructure.s3_client import S3Client


def _client_error(code="InternalError", op="UploadPart"):
    return ClientError({"Error": {"Code": code, "Message": "boom"}}, op)


def _fake_client():
    c = MagicMock()
    c.closed = False
    c.closed_when_aborted = None

    async def _abort(**kwargs):
        c.closed_when_aborted = c.closed

    c.create_multipart_upload = AsyncMock(return_value={"UploadId": "u1"})
    c.upload_part = AsyncMock(return_value={"ETag": "e1"})
    c.complete_multipart_upload = AsyncMock()
    c.abort_multipart_upload = AsyncMock(side_effect=_abort)
    c.delete_object = AsyncMock()
    c.head_object = AsyncMock(return_value={"ContentLength": 0})
    return c


def _s3(fake):
    client = S3Client(
        access_key="k",
        secret_key="s",
        endpoint_url="http://minio:9000",
        region_name="us-east-1",
        bucket_names=["videos", "video-thumbnails"],
    )

    class _Ctx:
        async def __aenter__(self):
            return fake

        async def __aexit__(self, *exc):
            fake.closed = True
            return False

    # Swap the real aiobotocore context manager for the fake above.
    client._get_client = lambda: _Ctx()  # type: ignore[assignment,return-value]
    return client


class TestUpload:
    @pytest.mark.asyncio
    async def test_a_failed_upload_raises(self, tmp_path: Path):
        """It used to log the error and return, so the caller committed a
        video row and queued an encode for an object that was never
        stored, and recorded a thumbnail path pointing at nothing."""
        fake = _fake_client()
        fake.upload_part = AsyncMock(side_effect=_client_error())
        f = tmp_path / "v.mp4"
        f.write_bytes(b"data")

        with f.open("rb") as handle:
            with pytest.raises(VideoUploadFailedError):
                await _s3(fake).upload_file("v.mp4", handle, "videos")

    @pytest.mark.asyncio
    async def test_a_failed_upload_aborts_while_the_session_is_open(
        self, tmp_path: Path
    ):
        fake = _fake_client()
        fake.upload_part = AsyncMock(side_effect=_client_error())
        f = tmp_path / "v.mp4"
        f.write_bytes(b"data")

        with f.open("rb") as handle:
            with pytest.raises(VideoUploadFailedError):
                await _s3(fake).upload_file("v.mp4", handle, "videos")

        fake.abort_multipart_upload.assert_awaited_once()
        # The abort used to sit outside the context manager, so it ran
        # against a closed client, failed too, and left the parts behind.
        assert fake.closed_when_aborted is False

    @pytest.mark.asyncio
    async def test_a_good_upload_completes_and_does_not_abort(self, tmp_path: Path):
        fake = _fake_client()
        f = tmp_path / "v.mp4"
        f.write_bytes(b"data")

        with f.open("rb") as handle:
            await _s3(fake).upload_file("v.mp4", handle, "videos")

        fake.complete_multipart_upload.assert_awaited_once()
        fake.abort_multipart_upload.assert_not_awaited()


class TestDownload:
    @pytest.mark.asyncio
    async def test_a_missing_object_is_not_an_empty_success(self):
        """Swallowing this ended the generator quietly, so the browser was
        handed an empty 200 instead of being told the file is not there."""
        fake = _fake_client()
        fake.head_object = AsyncMock(
            side_effect=_client_error(code="NoSuchKey", op="HeadObject")
        )

        with pytest.raises(FileNotFoundS3Error):
            async for _ in _s3(fake).download_file("missing.mp4", 1024, "videos"):
                pass

    @pytest.mark.asyncio
    async def test_other_storage_errors_are_reported_as_download_failures(self):
        fake = _fake_client()
        fake.head_object = AsyncMock(
            side_effect=_client_error(code="InternalError", op="HeadObject")
        )

        with pytest.raises(S3DownloadError):
            async for _ in _s3(fake).download_file("x.mp4", 1024, "videos"):
                pass


class TestDelete:
    @pytest.mark.asyncio
    async def test_a_failed_delete_raises(self):
        """delete_video wraps its deletions in a rollback that could never
        fire while this was swallowed."""
        fake = _fake_client()
        fake.delete_object = AsyncMock(side_effect=_client_error(op="DeleteObject"))

        with pytest.raises(S3DeletionError):
            await _s3(fake).delete_file("k", "videos")

    @pytest.mark.asyncio
    async def test_rejects_a_bucket_it_does_not_know(self):
        with pytest.raises(ValueError):
            await _s3(_fake_client()).delete_file("k", "somewhere-else")


class TestListKeys:
    @pytest.mark.asyncio
    async def test_returns_every_key_under_the_prefix(self):
        fake = _fake_client()

        class _Paginator:
            def paginate(self, **kwargs):
                async def gen():
                    yield {"Contents": [{"Key": "abc.mp4"}, {"Key": "abc/master.m3u8"}]}
                    yield {"Contents": [{"Key": "abc/stream_360p/seg_000.ts"}]}

                return gen()

        fake.get_paginator = MagicMock(return_value=_Paginator())

        keys = await _s3(fake).list_keys("abc", "videos")
        assert keys == [
            "abc.mp4",
            "abc/master.m3u8",
            "abc/stream_360p/seg_000.ts",
        ]

    @pytest.mark.asyncio
    async def test_an_empty_prefix_returns_nothing_rather_than_everything(self):
        fake = _fake_client()

        class _Paginator:
            def paginate(self, **kwargs):
                async def gen():
                    yield {}

                return gen()

        fake.get_paginator = MagicMock(return_value=_Paginator())
        assert await _s3(fake).list_keys("nothing-here", "videos") == []
