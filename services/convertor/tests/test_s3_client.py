"""
The convertor's object storage client.

This file had no tests at all, which is how it came to swallow a failed
upload and report success: the encode then announced a video as ready
whose media had never been stored.
"""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from botocore.exceptions import ClientError

from src.exceptions import PresignFailedError, UploadFailedError
from src.s3_client import S3Client


def _client_error(op="UploadPart", code="InternalError"):
    return ClientError({"Error": {"Code": code, "Message": "boom"}}, op)


def _s3(fake_client):
    """An S3Client whose _get_client yields the given fake."""
    client = S3Client(
        access_key="k",
        secret_key="s",
        endpoint_url="http://minio:9000",
        region_name="us-east-1",
        bucket_names=["videos"],
    )

    class _Ctx:
        async def __aenter__(self):
            return fake_client

        async def __aexit__(self, *exc):
            fake_client.closed = True
            return False

    client._get_client = lambda: _Ctx()  # type: ignore[assignment, return-value]
    return client


def _posix(key: str) -> str:
    return key.replace("\\", "/")


def _happy_client():
    c = MagicMock()
    c.closed = False
    c.closed_when_aborted = None

    async def _abort(**kwargs):
        c.closed_when_aborted = c.closed

    c.abort_multipart_upload = AsyncMock(side_effect=_abort)
    c.create_multipart_upload = AsyncMock(return_value={"UploadId": "u1"})
    c.upload_part = AsyncMock(return_value={"ETag": "e1"})
    c.complete_multipart_upload = AsyncMock()
    c.delete_object = AsyncMock()
    c.generate_presigned_url = AsyncMock(return_value="http://signed")
    return c


class TestUploadFile:
    @pytest.mark.asyncio
    async def test_uploads_and_completes(self, tmp_path: Path):
        fake = _happy_client()
        f = tmp_path / "seg.ts"
        f.write_bytes(b"data")

        with f.open("rb") as handle:
            await _s3(fake).upload_file("v1/seg.ts", handle, "videos")

        fake.complete_multipart_upload.assert_awaited_once()
        fake.abort_multipart_upload.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_a_failed_upload_raises_instead_of_reporting_success(
        self, tmp_path: Path
    ):
        """The whole point. It used to log the error and return None."""
        fake = _happy_client()
        fake.upload_part = AsyncMock(side_effect=_client_error())
        f = tmp_path / "seg.ts"
        f.write_bytes(b"data")

        with f.open("rb") as handle:
            with pytest.raises(UploadFailedError) as err:
                await _s3(fake).upload_file("v1/seg.ts", handle, "videos")

        assert err.value.key == "v1/seg.ts"

    @pytest.mark.asyncio
    async def test_a_failed_upload_aborts_its_multipart(self, tmp_path: Path):
        """Otherwise the parts linger, billed and invisible to a listing."""
        fake = _happy_client()
        fake.upload_part = AsyncMock(side_effect=_client_error())
        f = tmp_path / "seg.ts"
        f.write_bytes(b"data")

        with f.open("rb") as handle:
            with pytest.raises(UploadFailedError):
                await _s3(fake).upload_file("v1/seg.ts", handle, "videos")

        fake.abort_multipart_upload.assert_awaited_once()
        assert fake.abort_multipart_upload.await_args.kwargs["UploadId"] == "u1"
        # And it ran while the session was still open. The abort used to sit
        # outside the context manager, against a client already closed, so
        # the cleanup failed too and the parts were left behind.
        assert fake.closed_when_aborted is False

    @pytest.mark.asyncio
    async def test_an_abort_that_also_fails_does_not_hide_the_upload_error(
        self, tmp_path: Path
    ):
        fake = _happy_client()
        fake.upload_part = AsyncMock(side_effect=_client_error())
        fake.abort_multipart_upload = AsyncMock(
            side_effect=_client_error(op="AbortMultipartUpload")
        )
        f = tmp_path / "seg.ts"
        f.write_bytes(b"data")

        with f.open("rb") as handle:
            with pytest.raises(UploadFailedError):
                await _s3(fake).upload_file("v1/seg.ts", handle, "videos")

    @pytest.mark.asyncio
    async def test_rejects_a_bucket_it_does_not_know(self, tmp_path: Path):
        f = tmp_path / "seg.ts"
        f.write_bytes(b"data")
        with f.open("rb") as handle:
            with pytest.raises(ValueError):
                await _s3(_happy_client()).upload_file("k", handle, "not-ours")


class TestUploadDir:
    @pytest.mark.asyncio
    async def test_uploads_every_file_under_the_directory(self, tmp_path: Path):
        (tmp_path / "stream_360p").mkdir()
        (tmp_path / "master.m3u8").write_bytes(b"m")
        (tmp_path / "stream_360p" / "seg_000.ts").write_bytes(b"s")

        fake = _happy_client()
        await _s3(fake).upload_dir("vid", tmp_path, "videos")

        keys = {
            _posix(call.kwargs["Key"])
            for call in fake.create_multipart_upload.await_args_list
        }
        assert keys == {"vid/master.m3u8", "vid/stream_360p/seg_000.ts"}

    @pytest.mark.asyncio
    async def test_one_failed_object_fails_the_whole_directory(self, tmp_path: Path):
        """A half-written rendition set must not be reported as done."""
        (tmp_path / "a.ts").write_bytes(b"a")
        (tmp_path / "b.ts").write_bytes(b"b")

        fake = _happy_client()
        fake.upload_part = AsyncMock(side_effect=_client_error())

        with pytest.raises(UploadFailedError):
            await _s3(fake).upload_dir("vid", tmp_path, "videos")

    @pytest.mark.asyncio
    async def test_closes_every_file_it_opens(self, tmp_path: Path):
        """The handles used to be left to the garbage collector, one per
        segment, and a rendition set is hundreds of them."""
        for i in range(3):
            (tmp_path / f"seg_{i}.ts").write_bytes(b"x")

        opened: list = []
        real_open = Path.open

        def tracking_open(self, *a, **kw):
            handle = real_open(self, *a, **kw)
            opened.append(handle)
            return handle

        with patch.object(Path, "open", tracking_open):
            await _s3(_happy_client()).upload_dir("vid", tmp_path, "videos")

        assert len(opened) == 3
        assert all(h.closed for h in opened)


class TestPresign:
    @pytest.mark.asyncio
    async def test_returns_the_url(self):
        assert (
            await _s3(_happy_client()).generate_presigned_url("k", "videos")
            == "http://signed"
        )

    @pytest.mark.asyncio
    async def test_a_storage_failure_becomes_one_of_ours(self):
        """main.py only recognises AppError; a bare ClientError escaped it
        and left the video stuck in "processing" with no failed status."""
        fake = _happy_client()
        fake.generate_presigned_url = AsyncMock(
            side_effect=_client_error(op="GetObject")
        )
        with pytest.raises(PresignFailedError):
            await _s3(fake).generate_presigned_url("k", "videos")
