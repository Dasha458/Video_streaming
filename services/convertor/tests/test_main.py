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


class TestMetrics:
    """The registry the endpoint serves was empty.

    Prometheus scraped it, called the target up, and the only series under
    job="ffmpeg" were the five it writes about its own scrape -- nothing
    about encoding at all.
    """

    @staticmethod
    def _fresh():
        """A worker's metrics on a registry of this test's own."""
        from prometheus_client import CollectorRegistry

        from src.metrics import EncodeMetrics

        registry = CollectorRegistry()
        return EncodeMetrics(registry), registry

    def test_the_registry_is_not_empty(self):
        _, registry = self._fresh()
        names = {m.name for m in registry.collect()}
        assert "convertor_encodes_started" in names
        assert "convertor_encodes_finished" in names
        assert "convertor_encode_duration_seconds" in names

    def test_outcomes_are_counted_separately(self):
        metrics, registry = self._fresh()
        metrics.finished.labels(outcome="ready").inc()
        metrics.finished.labels(outcome="failed").inc()
        metrics.finished.labels(outcome="failed").inc()

        assert (
            registry.get_sample_value(
                "convertor_encodes_finished_total", {"outcome": "failed"}
            )
            == 2
        )
        assert (
            registry.get_sample_value(
                "convertor_encodes_finished_total", {"outcome": "ready"}
            )
            == 1
        )

    def test_the_duration_buckets_reach_past_a_minute(self):
        """The default buckets stop at ten seconds, which is less than a
        minute of video."""
        metrics, registry = self._fresh()
        metrics.duration.observe(900)

        assert (
            registry.get_sample_value(
                "convertor_encode_duration_seconds_bucket", {"le": "1800.0"}
            )
            == 1
        )

    @pytest.mark.asyncio
    async def test_a_failed_encode_is_counted_as_failed(self):
        import main as convertor_main

        before = (
            convertor_main.registry.get_sample_value(
                "convertor_encodes_finished_total", {"outcome": "failed"}
            )
            or 0.0
        )

        with (
            patch.object(convertor_main, "publish_status", AsyncMock()),
            patch.object(
                convertor_main, "prepare_dirs", AsyncMock(return_value=Path("/tmp/x"))
            ),
            patch.object(convertor_main, "cleanup_dirs", MagicMock()),
            patch.object(convertor_main, "get_s3_client") as get_client,
        ):
            get_client.return_value.generate_presigned_url = AsyncMock(
                side_effect=OSError("storage gone")
            )
            await convertor_main.encode_video("abc123.mp4")

        after = convertor_main.registry.get_sample_value(
            "convertor_encodes_finished_total", {"outcome": "failed"}
        )
        assert after == before + 1
        # And the worker is not left looking busy.
        assert (
            convertor_main.registry.get_sample_value("convertor_encodes_in_progress")
            == 0
        )
