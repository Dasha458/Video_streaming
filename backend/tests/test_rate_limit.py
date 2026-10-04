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


class TestSurvivingARedisRestart:
    """Redis forgets loaded scripts when it restarts.

    The sha was cached for the life of the process, so from the moment
    Redis came back every rate limited endpoint answered 500 -- login,
    registration, uploads -- until somebody restarted the application.
    Nothing noticed, because nothing had ever restarted Redis under a
    running backend.
    """

    @staticmethod
    def _limiter(evalsha):
        from redis.exceptions import NoScriptError  # noqa: F401

        from src.infrastructure.redis.rate_limiter import RateLimiter

        redis = AsyncMock()
        redis.script_load = AsyncMock(side_effect=["sha-1", "sha-2"])
        redis.evalsha = evalsha
        return RateLimiter(redis)

    @pytest.mark.asyncio
    async def test_a_dropped_script_is_loaded_again(self):
        from redis.exceptions import NoScriptError

        evalsha = AsyncMock(side_effect=[NoScriptError("NOSCRIPT"), 0])
        limiter = self._limiter(evalsha)

        blocked = await limiter.is_limited("1.2.3.4", "login", 5, 60)

        assert blocked is False
        assert evalsha.await_count == 2
        # The second attempt uses the sha from the reload, not the stale one.
        assert evalsha.await_args_list[1].args[0] == "sha-2"

    @pytest.mark.asyncio
    async def test_a_second_failure_is_not_swallowed(self):
        """If the script cannot be loaded at all, that is a real failure
        and the caller should see it rather than be let through."""
        from redis.exceptions import NoScriptError

        evalsha = AsyncMock(side_effect=[NoScriptError("x"), NoScriptError("x")])
        limiter = self._limiter(evalsha)

        with pytest.raises(NoScriptError):
            await limiter.is_limited("1.2.3.4", "login", 5, 60)


class TestTheLocalBlockCache:
    """It used to hold every block for a flat 60 seconds, with a comment
    saying it followed the window -- so a ten-second window locked an
    address out for a minute after Redis would have let it through."""

    @staticmethod
    def _limiter():
        from src.infrastructure.redis.rate_limiter import RateLimiter

        redis = AsyncMock()
        redis.script_load = AsyncMock(return_value="sha")
        redis.evalsha = AsyncMock(return_value=1)  # blocked
        return RateLimiter(redis), redis

    @pytest.mark.asyncio
    async def test_a_block_is_served_from_memory_while_it_lasts(self):
        limiter, redis = self._limiter()

        assert await limiter.is_limited("1.2.3.4", "login", 5, 60) is True
        assert await limiter.is_limited("1.2.3.4", "login", 5, 60) is True

        # The second answer came from memory: Redis was asked once.
        assert redis.evalsha.await_count == 1

    @pytest.mark.asyncio
    async def test_it_stops_being_served_once_the_window_has_passed(self, monkeypatch):
        import time as time_module

        limiter, redis = self._limiter()
        clock = [1000.0]
        monkeypatch.setattr(time_module, "monotonic", lambda: clock[0])

        assert await limiter.is_limited("1.2.3.4", "login", 5, 10) is True
        clock[0] += 11  # the ten-second window has passed

        redis.evalsha = AsyncMock(return_value=0)
        assert await limiter.is_limited("1.2.3.4", "login", 5, 10) is False
        redis.evalsha.assert_awaited_once()
