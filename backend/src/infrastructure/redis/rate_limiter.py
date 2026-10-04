import logging
import random
import time
from typing import Any, Awaitable, Optional, cast

from cachetools import TTLCache
from redis.asyncio import Redis
from redis.exceptions import NoScriptError


class RateLimiter:
    LUA_SCRIPT = """
    redis.call("ZREMRANGEBYSCORE", KEYS[1], 0, ARGV[2])
    local count = redis.call("ZCARD", KEYS[1])
    if count >= tonumber(ARGV[3]) then
        return 1
    end
    redis.call("ZADD", KEYS[1], ARGV[1], ARGV[5])
    redis.call("EXPIRE", KEYS[1], ARGV[4])
    return 0
    """

    #: Longest window any caller uses, and so the longest a local block
    #: may be remembered. The cache is shared by every endpoint, so one
    #: TTL has to cover them all; it used to be a flat 60 seconds with a
    #: comment claiming it followed window_seconds, which meant a
    #: ten-second window blocked an address for a minute.
    MAX_BLOCK_TTL = 300

    def __init__(self, redis: Redis):
        self._redis = redis
        self._lua_sha: Optional[str] = None
        # Up to 10,000 blocked addresses, each remembered only as long as
        # the window it was blocked for -- see _remember_block.
        self._local_block_cache: TTLCache = TTLCache(
            maxsize=10_000,
            ttl=self.MAX_BLOCK_TTL,
        )

    async def _get_script_sha(self) -> str:
        # redis-py types every command as `Awaitable[T] | T` because the async
        # client reuses the sync class; on Redis.asyncio it is always the
        # awaitable branch.
        if self._lua_sha is None:
            self._lua_sha = await cast(
                Awaitable[str], self._redis.script_load(self.LUA_SCRIPT)
            )
        return self._lua_sha

    async def is_limited(
        self,
        ip_address: str,
        endpoint: str,
        max_requests: int,
        window_seconds: int,
    ) -> bool:
        cache_key = f"{endpoint}:{ip_address}"

        blocked_until = self._local_block_cache.get(cache_key)
        if blocked_until is not None:
            if time.monotonic() < blocked_until:
                # Already known to be blocked; no need to talk to Redis.
                return True
            # The window has passed even though the cache entry has not.
            self._local_block_cache.pop(cache_key, None)

        current_ms = int(time.time() * 1000)
        window_start_ms = current_ms - (window_seconds * 1000)
        member_id = f"{current_ms}-{random.randint(0, 100000)}"
        args = (
            f"rate_limit:{cache_key}",  # Redis Key
            current_ms,
            window_start_ms,
            max_requests,
            window_seconds,
            member_id,
        )

        try:
            is_blocked_in_redis = await self._run(args)
        except NoScriptError:
            # Redis forgets loaded scripts when it restarts, and the sha
            # was cached for the life of the process -- so every rate
            # limited endpoint answered 500 from the moment Redis came
            # back until the application was restarted. Loading it again
            # is the documented response to NOSCRIPT.
            logging.info("Rate limit script was dropped by Redis; reloading it")
            self._lua_sha = None
            is_blocked_in_redis = await self._run(args)

        if is_blocked_in_redis == 1:
            self._remember_block(cache_key, window_seconds)
            return True

        return False

    async def _run(self, args: tuple) -> Any:
        sha = await self._get_script_sha()
        return await cast(Awaitable[Any], self._redis.evalsha(sha, 1, *args))

    def _remember_block(self, cache_key: str, window_seconds: int) -> None:
        """Keep the block locally for as long as it can actually last.

        A shared TTLCache has one expiry, so a per-entry deadline is kept
        alongside the entry and checked on read. Without it a block from
        a ten-second window was still being served from memory nearly a
        minute later, long after Redis would have let the caller through.
        """
        deadline = time.monotonic() + min(window_seconds, self.MAX_BLOCK_TTL)
        self._local_block_cache[cache_key] = deadline
