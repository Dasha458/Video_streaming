"""Tests for GET /api/health/live and GET /api/health/ready."""

from unittest.mock import AsyncMock, MagicMock

import pytest


class TestLivenessEndpoint:
    """GET /api/health/live — no dependencies, always 200."""

    def test_live_returns_200(self, client):
        response = client.get("/api/health/live")
        assert response.status_code == 200

    def test_live_body_has_status_ok(self, client):
        body = client.get("/api/health/live").json()
        assert body["status"] == "ok"

    def test_live_no_details(self, client):
        body = client.get("/api/health/live").json()
        # details is optional — either absent or null
        assert body.get("details") is None

    async def test_live_via_async_client(self, async_client):
        response = await async_client.get("/api/health/live")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"


class TestReadinessEndpoint:
    """GET /api/health/ready — checks DB, S3, broker."""

    def test_ready_returns_200_all_healthy(self, client):
        # All infra mocks succeed by default (mock_s3_client.get_bucket_list is
        # an AsyncMock that returns a list without raising)
        response = client.get("/api/health/ready")
        assert response.status_code == 200
        assert response.json()["status"] == "ready"

    def test_ready_response_contains_detail_keys(self, client):
        body = client.get("/api/health/ready").json()
        details = body.get("details", {})
        assert "database" in details
        assert "object_storage" in details
        assert "message_broker" in details

    def test_ready_all_checks_ok(self, client):
        body = client.get("/api/health/ready").json()
        details = body["details"]
        assert details["database"] == "ok"
        assert details["object_storage"] == "ok"

    def test_ready_returns_503_when_db_fails(self, client, app):
        from src.infrastructure import get_async_session

        def failing_session():
            session = AsyncMock()
            session.execute = AsyncMock(side_effect=Exception("DB unreachable"))
            return session

        original = app.dependency_overrides.get(get_async_session)
        app.dependency_overrides[get_async_session] = failing_session
        try:
            response = client.get("/api/health/ready")
            assert response.status_code == 503
            body = response.json()
            assert body["status"] == "not ready"
            assert body["details"]["database"] != "ok"
        finally:
            if original is not None:
                app.dependency_overrides[get_async_session] = original
            else:
                app.dependency_overrides.pop(get_async_session, None)

    def test_ready_returns_503_when_s3_fails(self, client, app):
        from src.infrastructure import get_s3_client

        failing_s3 = AsyncMock()
        failing_s3.get_bucket_list = AsyncMock(side_effect=Exception("S3 unreachable"))

        original = app.dependency_overrides.get(get_s3_client)
        app.dependency_overrides[get_s3_client] = lambda: failing_s3
        try:
            response = client.get("/api/health/ready")
            assert response.status_code == 503
            assert response.json()["status"] == "not ready"
        finally:
            if original is not None:
                app.dependency_overrides[get_s3_client] = original
            else:
                app.dependency_overrides.pop(get_s3_client, None)


class TestTheBrokerCheckObserves:
    """It used to call connect() when it found the broker disconnected.

    A readiness probe that changes the application's state is the wrong
    shape, and against a broker that was genuinely down it hammered
    connect() on every probe for the length of the outage. The second
    guard then defaulted to True, so a broker that reported nothing
    always passed -- a check that could not fail.
    """

    @staticmethod
    async def _check(broker):
        from src.services.health import HealthService

        service = HealthService(
            session=AsyncMock(), s3_client=AsyncMock(), broker=broker
        )
        await service._check_message_broker()
        return service

    @pytest.mark.asyncio
    async def test_a_broker_that_answers_passes(self):
        broker = MagicMock()
        broker.ping = AsyncMock(return_value=True)

        service = await self._check(broker)

        assert service.checks["message_broker"] == "ok"

    @pytest.mark.asyncio
    async def test_a_silent_broker_is_reported_not_reconnected(self):
        broker = MagicMock()
        broker.ping = AsyncMock(return_value=False)
        broker.connect = MagicMock()

        service = await self._check(broker)

        assert service.checks["message_broker"] != "ok"
        broker.connect.assert_not_called()

    @pytest.mark.asyncio
    async def test_the_probe_does_not_wait_on_a_slow_broker(self):
        """A readiness probe runs every few seconds; an unbounded wait
        here turns a slow broker into a slow probe."""
        broker = MagicMock()
        broker.ping = AsyncMock(return_value=True)

        await self._check(broker)

        assert broker.ping.await_args.kwargs["timeout"] <= 5

    @pytest.mark.asyncio
    async def test_a_broker_with_nothing_to_ask_is_not_called_healthy(self):
        broker = MagicMock(spec=[])  # no ping, no is_connected

        service = await self._check(broker)

        assert service.checks["message_broker"] == "unknown"
