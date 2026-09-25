"""
Analytics API — YouTube-Studio-style creator dashboard.

Every endpoint resolves the authenticated user's channel via
``get_service_and_channel`` and returns a 404 if the user has no channel
yet.  Period-aware endpoints accept a ``?period=7d|28d|90d|365d|all``
query parameter (default ``28d``, matching YouTube Studio's default).
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import JSONResponse

from src.api.dependencies.services import (
    get_analytics_service,
    get_service_and_channel,
)
from src.schemas.analytics import (
    AudienceResponse,
    ContentResponse,
    EngagementResponse,
    OverviewResponse,
    Period,
    RealtimeResponse,
    TrafficSourcesResponse,
    VideoAnalyticsResponse,
    WatchSessionAck,
    WatchSessionPing,
)
from src.services.analytics import AnalyticsService
from src.services.dependencies import get_optional_user_id

router_analytics = APIRouter(
    prefix="/api/analytics",
    tags=["analytics"],
    default_response_class=JSONResponse,
    responses={
        401: {"description": "Not authenticated"},
        404: {"description": "Channel not found"},
        500: {"description": "Internal server error"},
    },
)


def _require_channel(deps: tuple) -> tuple:
    service, channel = deps
    if channel is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Channel not found for current user",
        )
    return service, channel


# ── Dashboard tabs ──────────────────────────────────────────────────────────


@router_analytics.get("/overview", response_model=OverviewResponse)
async def analytics_overview(
    period: Period = Query(Period.LAST_28, description="Reporting window"),
    deps: tuple = Depends(get_service_and_channel),
) -> OverviewResponse:
    service, channel = _require_channel(deps)
    return await service.get_overview(channel, period)


@router_analytics.get("/content", response_model=ContentResponse)
async def analytics_content(
    period: Period = Query(Period.LAST_28, description="Reporting window"),
    deps: tuple = Depends(get_service_and_channel),
) -> ContentResponse:
    service, channel = _require_channel(deps)
    return await service.get_content(channel, period)


@router_analytics.get("/audience", response_model=AudienceResponse)
async def analytics_audience(
    period: Period = Query(Period.LAST_28, description="Reporting window"),
    deps: tuple = Depends(get_service_and_channel),
) -> AudienceResponse:
    service, channel = _require_channel(deps)
    return await service.get_audience(channel, period)


@router_analytics.get("/engagement", response_model=EngagementResponse)
async def analytics_engagement(
    period: Period = Query(Period.LAST_28, description="Reporting window"),
    deps: tuple = Depends(get_service_and_channel),
) -> EngagementResponse:
    """Watch time, average view duration, retention %, engagement rate."""
    service, channel = _require_channel(deps)
    return await service.get_engagement(channel, period)


@router_analytics.get("/realtime", response_model=RealtimeResponse)
async def analytics_realtime(
    deps: tuple = Depends(get_service_and_channel),
) -> RealtimeResponse:
    """Views in the last 48 hours (per-hour) and last 60 minutes."""
    service, channel = _require_channel(deps)
    return await service.get_realtime(channel)


@router_analytics.get("/traffic-sources", response_model=TrafficSourcesResponse)
async def analytics_traffic_sources(
    period: Period = Query(Period.LAST_28, description="Reporting window"),
    deps: tuple = Depends(get_service_and_channel),
) -> TrafficSourcesResponse:
    """Breakdown of views by traffic source (direct / search / recommendation / …)."""
    service, channel = _require_channel(deps)
    return await service.get_traffic_sources(channel, period)


# ── Per-video deep dive ─────────────────────────────────────────────────────


@router_analytics.get(
    "/videos/{video_id}",
    response_model=VideoAnalyticsResponse,
    responses={404: {"description": "Video not found on this channel"}},
)
async def analytics_video_detail(
    video_id: UUID,
    period: Period = Query(Period.LAST_28, description="Reporting window"),
    deps: tuple = Depends(get_service_and_channel),
) -> VideoAnalyticsResponse:
    service, channel = _require_channel(deps)
    result = await service.get_video_analytics(channel, video_id, period)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Video not found on this channel",
        )
    return result


# ── Watch-session heartbeat ─────────────────────────────────────────────────


@router_analytics.post(
    "/watch-session",
    response_model=WatchSessionAck,
    status_code=status.HTTP_200_OK,
    responses={
        200: {"description": "Heartbeat accepted"},
        422: {"description": "Invalid payload"},
    },
)
async def record_watch_session(
    payload: WatchSessionPing,
    user_id: UUID | None = Depends(get_optional_user_id),
    service: AnalyticsService = Depends(get_analytics_service),
) -> WatchSessionAck:
    """
    Called by the video player roughly every ten seconds while playback
    is active.  Cumulative — the client reports the latest
    ``watched_seconds`` cursor for a stable ``session_id``.  Anonymous
    sessions are allowed (``user_id`` may be ``None``).
    """
    return await service.record_watch_session(payload, user_id)
