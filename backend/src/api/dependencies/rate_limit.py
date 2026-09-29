from collections.abc import Awaitable, Callable
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.requests import Request
from redis.asyncio import Redis

from src.core.client_address import client_ip
from src.infrastructure import get_redis
from src.infrastructure.redis.rate_limiter import RateLimiter


async def get_rate_limiter(redis: Redis = Depends(get_redis)) -> RateLimiter:
    return RateLimiter(redis)


def limit_requests(
    endpoint: str, max_requests: int, window_seconds: int
) -> Callable[..., Awaitable[None]]:
    """
    Factory function to create a custom dependency for each endpoint
    Example usage:
    @router_files.post(
        "/upload",
        response_model=UploadResponse,
        dependencies=[Depends(limit_requests("upload_files", max_requests=5, window_seconds=60))]
    )
    """

    async def dependency(
        request: Request,
        limiter: Annotated[RateLimiter, Depends(get_rate_limiter)],
    ) -> None:
        # Was request.client.host, which behind the gateway is the gateway
        # itself: every caller shared a single bucket, so five uploads a
        # minute was a limit on the whole platform and one user could lock
        # everyone else out.
        identifier = client_ip(request)

        is_limited = await limiter.is_limited(
            ip_address=identifier,
            endpoint=endpoint,
            max_requests=max_requests,
            window_seconds=window_seconds,
        )

        if is_limited:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many requests. Please cool down.",
            )

    return dependency
