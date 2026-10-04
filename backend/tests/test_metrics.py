"""The metrics endpoint is only useful if the series are actually there.

Prometheus reported the target up all along; what it scraped was another
question. These assert the two things a dashboard depends on: the
endpoint serves the exposition format, and a counter nobody has
incremented yet still reads as zero rather than as nothing at all.
"""

from prometheus_client import REGISTRY

from src.services.metrics import APP_NAME


def test_an_unused_search_counter_reads_as_zero():
    """Otherwise an hour with no searches is indistinguishable, on screen,
    from a scrape that is down."""
    import src.schemas.metric  # noqa: F401  (declares the label)

    value = REGISTRY.get_sample_value(
        "video_search_requests_total", {"category": "none"}
    )
    assert value == 0


def test_the_endpoint_serves_the_application_series(client):
    # The request metrics carry a path label, so they do not exist until
    # at least one request has gone through the middleware. Any route
    # will do -- a 404 is still a request.
    client.get("/api/nothing-is-served-here")

    response = client.get("/api/metrics")

    assert response.status_code == 200
    assert "text/plain" in response.headers["content-type"]

    body = response.text
    for name in (
        "fastapi_requests_total",
        "fastapi_responses_total",
        "fastapi_requests_duration_seconds_bucket",
        "fastapi_requests_in_progress",
        "video_search_requests_total",
    ):
        assert name in body, f"{name} is not exposed"


class TestWhatTheCountersCount:
    """fastapi_requests_total was incremented only on success.

    So the total undercounted by exactly the failures, and every "share
    of errors" computed against it -- including the alert that pages
    somebody -- was wrong in the direction that hides the problem.
    """

    @staticmethod
    def _total(path: str) -> float:
        return (
            REGISTRY.get_sample_value(
                "fastapi_requests_total",
                {"method": "GET", "path": path, "app_name": APP_NAME},
            )
            or 0.0
        )

    def test_a_request_that_fails_is_still_a_request(self, client, app):
        from fastapi import APIRouter

        router = APIRouter()

        @router.get("/api/boom-for-metrics")
        async def boom():
            raise RuntimeError("deliberate")

        app.include_router(router)
        app.router.routes = app.router.routes  # routing cache is per-request

        before = self._total("/api/boom-for-metrics")
        client.get("/api/boom-for-metrics")
        after = self._total("/api/boom-for-metrics")

        assert after == before + 1

    def test_a_successful_request_is_counted_once(self, client, app):
        before = self._total("/api/videos/categories")
        client.get("/api/videos/categories")
        after = self._total("/api/videos/categories")

        assert after == before + 1

    def test_the_path_label_is_the_template_not_the_id(self, client, app):
        """A label carrying real video ids would create a series per row
        and take Prometheus down."""
        video_id = "11111111-1111-1111-1111-111111111111"
        client.get(f"/api/videos/{video_id}")

        labels = {
            sample.labels["path"]
            for metric in REGISTRY.collect()
            if metric.name == "fastapi_requests"
            for sample in metric.samples
        }
        assert video_id not in " ".join(labels)
