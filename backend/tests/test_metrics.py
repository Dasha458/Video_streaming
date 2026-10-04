"""The metrics endpoint is only useful if the series are actually there.

Prometheus reported the target up all along; what it scraped was another
question. These assert the two things a dashboard depends on: the
endpoint serves the exposition format, and a counter nobody has
incremented yet still reads as zero rather than as nothing at all.
"""

from prometheus_client import REGISTRY


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
