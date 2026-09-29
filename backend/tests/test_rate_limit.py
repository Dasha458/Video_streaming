"""
Per-endpoint rate limiting.

It was keyed on ``request.client.host``, which behind the gateway is the
gateway's own address. Every caller therefore shared one bucket: "five
uploads a minute" was a limit on the whole platform, and one user could
lock everyone else out of uploading.
"""

from unittest.mock import AsyncMock

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from src.api.dependencies.rate_limit import get_rate_limiter, limit_requests
from src.core.client_address import REAL_IP_HEADER


@pytest.fixture
def limiter():
    fake = AsyncMock()
    fake.is_limited = AsyncMock(return_value=False)
    return fake


@pytest.fixture
def client(limiter):
    app = FastAPI()

    @app.get(
        "/guarded",
        dependencies=[
            Depends(limit_requests("guarded", max_requests=5, window_seconds=60))
        ],
    )
    async def guarded() -> dict:
        return {"ok": True}

    app.dependency_overrides[get_rate_limiter] = lambda: limiter
    return TestClient(app)


def _keys(limiter) -> list[str]:
    return [c.kwargs["ip_address"] for c in limiter.is_limited.await_args_list]


class TestBucketing:
    def test_two_callers_get_two_buckets(self, client, limiter):
        """The whole point: they used to share one."""
        client.get("/guarded", headers={REAL_IP_HEADER: "203.0.113.1"})
        client.get("/guarded", headers={REAL_IP_HEADER: "203.0.113.2"})

        assert _keys(limiter) == ["203.0.113.1", "203.0.113.2"]

    def test_the_same_caller_keeps_one_bucket(self, client, limiter):
        for _ in range(3):
            client.get("/guarded", headers={REAL_IP_HEADER: "203.0.113.1"})

        assert set(_keys(limiter)) == {"203.0.113.1"}

    def test_x_forwarded_for_is_not_consulted(self, client, limiter):
        """Its first entry is whatever the caller wrote, so trusting it
        would let one caller mint a fresh bucket per request and never be
        limited at all."""
        client.get(
            "/guarded",
            headers={
                REAL_IP_HEADER: "203.0.113.1",
                "X-Forwarded-For": "9.9.9.9, 10.0.0.1",
            },
        )
        assert _keys(limiter) == ["203.0.113.1"]


class TestOutcome:
    def test_a_limited_caller_gets_429(self, client, limiter):
        limiter.is_limited = AsyncMock(return_value=True)
        response = client.get("/guarded", headers={REAL_IP_HEADER: "203.0.113.1"})
        assert response.status_code == 429

    def test_an_unlimited_caller_passes_through(self, client):
        response = client.get("/guarded", headers={REAL_IP_HEADER: "203.0.113.1"})
        assert response.status_code == 200

    def test_the_endpoint_and_limits_reach_the_limiter(self, client, limiter):
        client.get("/guarded", headers={REAL_IP_HEADER: "203.0.113.1"})
        call = limiter.is_limited.await_args.kwargs
        assert call["endpoint"] == "guarded"
        assert call["max_requests"] == 5
        assert call["window_seconds"] == 60
