import asyncio
from typing import TYPE_CHECKING, Dict, Optional

from fastapi import status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.errors.health import (
    DatabaseUnavailableError,
    MessageBrokerUnavailableError,
    ObjectStorageUnavailableError,
)
from src.schemas.endpoint import HealthStatus

if TYPE_CHECKING:
    from faststream.rabbit import RabbitBroker

    from src.infrastructure.s3_client import S3Client


class HealthService:
    def __init__(
        self,
        session: AsyncSession,
        s3_client: "S3Client",
        broker: Optional["RabbitBroker"] = None,
    ):
        self.session = session
        self.s3_client = s3_client
        self.broker = broker
        self.checks: Dict[str, str] = {}
        self._statuses: list[int] = []
        self.status_code = status.HTTP_200_OK

    async def _check_database(self) -> None:
        try:
            await self.session.execute(text("SELECT 1"))
            self.checks["database"] = "ok"
        except Exception as ex:
            err = DatabaseUnavailableError(ex)
            self.checks["database"] = err.code
            self._statuses.append(err.status_code)

    async def _check_object_storage(self) -> None:
        try:
            await self.s3_client.get_bucket_list()
            self.checks["object_storage"] = "ok"
        except Exception as ex:
            err = ObjectStorageUnavailableError(ex)
            self.checks["object_storage"] = err.code
            self._statuses.append(err.status_code)

    #: A readiness probe runs every few seconds; waiting longer than this
    #: for an answer turns a slow broker into a slow probe.
    BROKER_PING_TIMEOUT = 2.0

    async def _check_message_broker(self) -> None:
        if self.broker is None:
            self.checks["message_broker"] = "skipped"
            return

        try:
            # Reported, not repaired. This used to call connect() when it
            # found the broker disconnected, so a readiness probe changed
            # the state of the application -- and against a broker that
            # was actually down it hammered connect() on every probe,
            # several times a minute, for as long as the outage lasted.
            # Reconnecting is the broker client's own job; saying so is
            # this function's.
            ping = getattr(self.broker, "ping", None)
            if ping is None:
                # Nothing to ask. "unknown" is the honest answer; the
                # old default here was True, which made this a check
                # that could not fail.
                self.checks["message_broker"] = "unknown"
                return

            # The client's own liveness call, which neither opens nor
            # closes anything. It also replaces the `is_connected`
            # attribute this used to read -- FastStream's RabbitBroker
            # does not have one, so the check was answering from a
            # default and passing while the broker was down.
            if not await ping(timeout=self.BROKER_PING_TIMEOUT):
                raise RuntimeError("Message broker did not answer")

            self.checks["message_broker"] = "ok"
        except Exception as ex:
            err = MessageBrokerUnavailableError(ex)
            self.checks["message_broker"] = err.code
            self._statuses.append(err.status_code)

    async def check_health(self) -> HealthStatus:
        await asyncio.gather(
            self._check_database(),
            self._check_object_storage(),
            self._check_message_broker(),
        )

        self.status_code = (
            status.HTTP_200_OK if not self._statuses else max(self._statuses)
        )

        return HealthStatus(
            status="ready" if self.status_code == 200 else "not ready",
            details=self.checks,
        )
