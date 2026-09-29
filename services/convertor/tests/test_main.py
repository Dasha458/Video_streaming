from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from botocore.exceptions import ClientError

from src.exceptions import DirectoryCleanupError
from src.services import cleanup_dirs, prepare_dirs


@pytest.mark.asyncio
async def test_prepare_and_cleanup_dirs() -> None:
    vid = "testvid"
    path = await prepare_dirs(vid)
    assert path.exists()
    cleanup_dirs(vid)
    assert not path.exists()


class TestFailureReporting:
    """Whatever goes wrong, the backend has to be told.

    Encoding used to report a failure only for the service's own AppError
    subclasses. A botocore ClientError, an OSError, or the ValueError that
    a malformed frame rate produces all escaped the handler, so no
    "failed" status was published and the video stayed in "processing"
    for good -- a state its owner cannot even delete from.
    """

    @staticmethod
    async def _run_encode(failure: Exception) -> list:
        import main as convertor_main

        published: list = []

        async def capture(message):
            published.append(message)

        with (
            patch.object(convertor_main, "publish_status", capture),
            patch.object(
                convertor_main, "prepare_dirs", AsyncMock(return_value=Path("/tmp/x"))
            ),
            patch.object(convertor_main, "cleanup_dirs", MagicMock()),
            patch.object(convertor_main, "get_s3_client") as get_client,
        ):
            get_client.return_value.generate_presigned_url = AsyncMock(
                side_effect=failure
            )
            await convertor_main.encode_video("abc123.mp4")

        return published

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "failure",
        [
            ClientError({"Error": {"Code": "InternalError"}}, "GetObject"),
            OSError("disk went away"),
            ValueError("invalid literal for int()"),
            RuntimeError("something nobody predicted"),
        ],
        ids=["botocore", "os", "value", "runtime"],
    )
    async def test_any_failure_is_reported_as_failed(self, failure):
        published = await self._run_encode(failure)

        statuses = [m.status for m in published]
        assert "failed" in statuses, f"{type(failure).__name__} was never reported"
        assert statuses[-1] == "failed"

    @pytest.mark.asyncio
    async def test_a_broker_that_cannot_report_does_not_take_the_worker_down(self):
        """The one failure that cannot report itself is the broker's own."""
        import main as convertor_main

        with (
            patch.object(
                convertor_main, "publish_status", AsyncMock(side_effect=OSError("down"))
            ),
            patch.object(
                convertor_main, "prepare_dirs", AsyncMock(return_value=Path("/tmp/x"))
            ),
            patch.object(convertor_main, "cleanup_dirs", MagicMock()),
            patch.object(convertor_main, "get_s3_client"),
        ):
            # Must not raise.
            await convertor_main.encode_video("abc123.mp4")

    @pytest.mark.asyncio
    async def test_a_cleanup_failure_does_not_replace_the_outcome(self):
        """cleanup runs in `finally`; raising there used to mask the result."""
        import main as convertor_main

        published: list = []

        async def capture(message):
            published.append(message)

        with (
            patch.object(convertor_main, "publish_status", capture),
            patch.object(
                convertor_main, "prepare_dirs", AsyncMock(return_value=Path("/tmp/x"))
            ),
            patch.object(
                convertor_main,
                "cleanup_dirs",
                MagicMock(side_effect=DirectoryCleanupError("abc123")),
            ),
            patch.object(convertor_main, "get_s3_client") as get_client,
        ):
            get_client.return_value.generate_presigned_url = AsyncMock(
                side_effect=OSError("nope")
            )
            await convertor_main.encode_video("abc123.mp4")

        assert [m.status for m in published][-1] == "failed"
