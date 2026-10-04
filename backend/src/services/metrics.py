import time
from typing import Callable, List

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.routing import Match

from src.schemas.metric import (
    EXCEPTIONS_TOTAL,
    REQUEST_DURATION_HIST,
    REQUESTS_IN_PROGRESS,
    REQUESTS_TOTAL,
    RESPONSES_TOTAL,
)

EXCLUDE_PATH_PREFIXES: List[str] = [
    "/api/metrics",
    "/api/health",
    "/static",
    "/docs",
    "/openapi.json",
]

APP_NAME = "FastAPI Video Streaming"


def is_excluded_path(path: str) -> bool:
    return any(path.startswith(p) for p in EXCLUDE_PATH_PREFIXES)


def get_route_path(request: Request) -> str:
    """The templated path (/videos/{id}), not the actual URL.

    The id matters: a label carrying real video ids would create a
    Prometheus series per row and take the whole thing down.

    Starlette records the matched route on the scope while handling the
    request, so once the handler has run the answer is simply there.
    This used to walk every route in the application and re-run its
    matcher -- around sixty regular expressions per request, on the hot
    path, to recompute something routing had already worked out.
    """
    route = request.scope.get("route")
    path = getattr(route, "path", None)
    if path:
        return str(path)
    # Before the handler runs, or for a request that matched nothing at
    # all: fall back to matching by hand. A 404 has no route, and its raw
    # URL is attacker-controlled, so it is bucketed rather than labelled.
    for candidate in request.app.routes:
        match, _ = candidate.matches(request.scope)
        if match == Match.FULL:
            return str(candidate.path)
    return "unmatched"


class PrometheusMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        if is_excluded_path(request.url.path):
            return await call_next(request)

        method = request.method
        # Counted before the handler runs, so a request that raises is
        # still a request. This used to be incremented only on success,
        # which meant fastapi_requests_total undercounted by exactly the
        # failures -- and every "share of errors" computed against it was
        # wrong in the direction that hides the problem.
        in_progress_label = get_route_path(request)
        REQUESTS_IN_PROGRESS.labels(
            method=method, path=in_progress_label, app_name=APP_NAME
        ).inc()

        start = time.perf_counter()
        path_label = in_progress_label

        try:
            response = await call_next(request)
            # Re-read after the handler: by now routing has recorded the
            # matched route on the scope, so this is the templated path
            # rather than a guess.
            path_label = get_route_path(request)
            status_code = str(response.status_code)

            RESPONSES_TOTAL.labels(
                status_code=status_code,
                method=method,
                path=path_label,
                app_name=APP_NAME,
            ).inc()

            return response

        except Exception as exc:
            path_label = get_route_path(request)
            exc_type = type(exc).__name__
            EXCEPTIONS_TOTAL.labels(
                exception_type=exc_type,
                method=method,
                path=path_label,
                app_name=APP_NAME,
            ).inc()
            raise

        finally:
            REQUESTS_TOTAL.labels(
                method=method, path=path_label, app_name=APP_NAME
            ).inc()

            duration = time.perf_counter() - start
            REQUEST_DURATION_HIST.labels(
                method=method, path=path_label, app_name=APP_NAME
            ).observe(duration)

            REQUESTS_IN_PROGRESS.labels(
                method=method, path=in_progress_label, app_name=APP_NAME
            ).dec()
