"""
Real-Postgres tests for AnalyticsService's windowed/delta queries -- the
part of stage 3's refactor (_windowed, _scalar_count) a mocked session
can't actually verify, since the interesting behaviour IS the SQL: joins,
date filtering, and comparing a period against the one before it.
"""

import uuid
from datetime import timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.schemas.analytics import Period
from src.services.analytics import AnalyticsService
from tests.integration.conftest import (
    REACTION_DISLIKE_ID,
    REACTION_LIKE_ID,
    add_reaction,
    add_view,
    add_watch_session,
    make_channel,
    make_user,
    make_video,
    now,
)

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_overview_counts_views_only_inside_the_channel(session: AsyncSession):
    owner = await make_user(session)
    other = await make_user(session)
    channel = await make_channel(session, owner)
    other_channel = await make_channel(session, other)
    video = await make_video(session, channel)
    other_video = await make_video(session, other_channel)

    await add_view(session, video, at=now())
    await add_view(session, video, at=now())
    await add_view(session, other_video, at=now())  # must not leak in

    service = AnalyticsService(session)
    overview = await service.get_overview(channel, Period.LAST_28)

    assert overview.total_views.value == 2


@pytest.mark.asyncio
async def test_overview_delta_compares_current_window_to_the_one_before_it(
    session: AsyncSession,
):
    owner = await make_user(session)
    channel = await make_channel(session, owner)
    video = await make_video(session, channel)

    # 3 views in the last 7 days (current window), 1 view 10 days ago
    # (previous window -- period.days=7 means prev window is days 7-14 ago).
    for _ in range(3):
        await add_view(session, video, at=now() - timedelta(days=1))
    await add_view(session, video, at=now() - timedelta(days=10))

    service = AnalyticsService(session)
    overview = await service.get_overview(channel, Period.LAST_7)

    assert overview.total_views.value == 3
    assert overview.total_views.previous == 1
    assert overview.total_views.delta_percent == 200.0  # (3-1)/1 * 100


@pytest.mark.asyncio
async def test_overview_period_all_has_no_previous_window(session: AsyncSession):
    owner = await make_user(session)
    channel = await make_channel(session, owner)
    video = await make_video(session, channel)
    await add_view(session, video, at=now() - timedelta(days=400))

    service = AnalyticsService(session)
    overview = await service.get_overview(channel, Period.ALL)

    assert overview.total_views.value == 1
    assert overview.total_views.previous == 0


@pytest.mark.asyncio
async def test_overview_top_videos_ranked_by_views_desc(session: AsyncSession):
    owner = await make_user(session)
    channel = await make_channel(session, owner)
    popular = await make_video(session, channel, name="popular")
    quiet = await make_video(session, channel, name="quiet")

    for _ in range(5):
        await add_view(session, popular, at=now())
    await add_view(session, quiet, at=now())

    service = AnalyticsService(session)
    overview = await service.get_overview(channel, Period.LAST_28)

    assert [v.title for v in overview.top_videos[:2]] == ["popular", "quiet"]
    assert overview.top_videos[0].views_count == 5


@pytest.mark.asyncio
async def test_content_reports_privacy_and_per_video_counts(session: AsyncSession):
    from src.core.status_ids import PRIVACY_PRIVATE_ID

    owner = await make_user(session)
    channel = await make_channel(session, owner)
    public_video = await make_video(session, channel, name="pub")
    await make_video(session, channel, name="priv", privacy_id=PRIVACY_PRIVATE_ID)

    viewer = await make_user(session)
    await add_reaction(session, public_video, viewer, reaction_id=REACTION_LIKE_ID)
    await add_reaction(session, public_video, owner, reaction_id=REACTION_DISLIKE_ID)

    service = AnalyticsService(session)
    content = await service.get_content(channel, Period.LAST_28)

    by_title = {v.title: v for v in content.videos}
    assert by_title["pub"].privacy == "public"
    assert by_title["priv"].privacy == "private"
    assert by_title["pub"].likes_count == 1
    assert by_title["pub"].dislikes_count == 1


@pytest.mark.asyncio
async def test_video_analytics_deltas_and_retention_for_one_video(
    session: AsyncSession,
):
    owner = await make_user(session)
    channel = await make_channel(session, owner)
    video = await make_video(session, channel)
    viewer = await make_user(session)

    await add_view(session, video, at=now() - timedelta(days=1))
    await add_view(session, video, at=now() - timedelta(days=1))
    await add_view(session, video, at=now() - timedelta(days=10))  # previous window
    await add_reaction(session, video, viewer, reaction_id=REACTION_LIKE_ID)
    await add_watch_session(
        session, video, watched=90, duration=100, at=now() - timedelta(days=1)
    )
    await add_watch_session(
        session, video, watched=20, duration=100, at=now() - timedelta(days=1)
    )

    service = AnalyticsService(session)
    result = await service.get_video_analytics(channel, video.id, Period.LAST_7)

    assert result is not None
    assert result.views.value == 2
    assert result.views.previous == 1
    assert result.likes.value == 1
    assert result.dislikes.value == 0
    # retention >= 75% should count exactly the 90%-watched session
    bucket_75 = next(b for b in result.retention if b.percent == 75)
    assert bucket_75.viewers == 1


@pytest.mark.asyncio
async def test_video_analytics_returns_none_for_a_video_outside_the_channel(
    session: AsyncSession,
):
    owner = await make_user(session)
    other_owner = await make_user(session)
    channel = await make_channel(session, owner)
    other_channel = await make_channel(session, other_owner)
    foreign_video = await make_video(session, other_channel)

    service = AnalyticsService(session)
    result = await service.get_video_analytics(
        channel, foreign_video.id, Period.LAST_28
    )

    assert result is None


@pytest.mark.asyncio
async def test_video_analytics_returns_none_for_an_unknown_video_id(
    session: AsyncSession,
):
    owner = await make_user(session)
    channel = await make_channel(session, owner)

    service = AnalyticsService(session)
    result = await service.get_video_analytics(channel, uuid.uuid4(), Period.LAST_28)

    assert result is None


@pytest.mark.asyncio
async def test_traffic_sources_percentages_sum_to_roughly_100(session: AsyncSession):
    owner = await make_user(session)
    channel = await make_channel(session, owner)
    video = await make_video(session, channel)

    for _ in range(3):
        await add_view(session, video, at=now(), source="search")
    await add_view(session, video, at=now(), source="direct")

    service = AnalyticsService(session)
    sources = await service.get_traffic_sources(channel, Period.LAST_28)

    total_pct = sum(s.percentage for s in sources.sources)
    assert 99.0 <= total_pct <= 100.0
    by_source = {s.source: s for s in sources.sources}
    assert by_source["search"].views == 3
    assert by_source["direct"].views == 1
