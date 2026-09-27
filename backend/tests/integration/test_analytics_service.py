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

from src.schemas.analytics import Period, WatchSessionPing
from src.services.analytics import AnalyticsService
from tests.integration.conftest import (
    REACTION_DISLIKE_ID,
    REACTION_LIKE_ID,
    add_comment,
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


@pytest.mark.asyncio
async def test_percent_viewed_survives_the_round_trip(session: AsyncSession):
    """What record_watch_session writes is what the reports read back.

    completed_percent is a percentage, 0-100. The reports used to treat it
    as a 0.0-1.0 fraction and multiply by 100, so a video watched to the
    end was reported as 10000 % and every retention bucket matched every
    session. Writing through the real service and reading through the real
    query is the only way to catch a disagreement between the two.
    """
    owner = await make_user(session)
    channel = await make_channel(session, owner)
    video = await make_video(session, channel)

    service = AnalyticsService(session)
    await service.record_watch_session(
        WatchSessionPing(
            session_id=uuid.uuid4(),
            video_id=video.id,
            watched_seconds=100,
            video_duration_seconds=100,
        ),
        user_id=owner.id,
    )

    engagement = await service.get_engagement(channel, Period.LAST_7)
    assert engagement.average_percent_viewed == 100.0

    detail = await service.get_video_analytics(channel, video.id, Period.LAST_7)
    assert detail is not None
    assert detail.average_percent_viewed == 100.0
    # A session watched to the end belongs in every bucket, including 100 %.
    assert [b.viewers for b in detail.retention] == [1, 1, 1, 1, 1]


@pytest.mark.asyncio
async def test_retention_buckets_split_on_the_right_boundary(session: AsyncSession):
    owner = await make_user(session)
    channel = await make_channel(session, owner)
    video = await make_video(session, channel)

    # 40 % watched: counts towards 10 and 25, not towards 50, 75 or 100.
    await add_watch_session(session, video, watched=40, duration=100)

    detail = await AnalyticsService(session).get_video_analytics(
        channel, video.id, Period.LAST_7
    )
    assert detail is not None
    assert {b.percent: b.viewers for b in detail.retention} == {
        10: 1,
        25: 1,
        50: 0,
        75: 0,
        100: 0,
    }


@pytest.mark.asyncio
async def test_daily_series_bucket_by_day_and_pad_the_gaps(session: AsyncSession):
    """The six per-day charts share one query builder now.

    Each of them used to be written out separately, so a change to how a
    day is bucketed could reach five and miss the sixth. These assertions
    are what makes the shared version safe to rely on.
    """
    owner = await make_user(session)
    viewer_a = await make_user(session)
    viewer_b = await make_user(session)
    channel = await make_channel(session, owner)
    video = await make_video(session, channel)

    today = now()
    await add_view(session, video, user=viewer_a, at=today)
    await add_view(session, video, user=viewer_b, at=today)
    # Two days ago, leaving yesterday empty on purpose.
    await add_view(session, video, at=today - timedelta(days=2))

    overview = await AnalyticsService(session).get_overview(channel, Period.LAST_7)
    series = {d.date: d.count for d in overview.views_per_day}

    assert series[today.date().isoformat()] == 2
    assert series[(today - timedelta(days=1)).date().isoformat()] == 0
    assert series[(today - timedelta(days=2)).date().isoformat()] == 1
    # Padded across the whole window, not just the days with activity.
    assert len(overview.views_per_day) == 8


@pytest.mark.asyncio
async def test_watch_time_and_percent_series_use_their_own_aggregates(
    session: AsyncSession,
):
    owner = await make_user(session)
    channel = await make_channel(session, owner)
    video = await make_video(session, channel)

    await add_watch_session(session, video, watched=30, duration=100)
    await add_watch_session(session, video, watched=70, duration=100)

    engagement = await AnalyticsService(session).get_engagement(channel, Period.LAST_7)
    today = now().date().isoformat()

    seconds = {d.date: d.count for d in engagement.watch_time_per_day}
    percent = {d.date: d.count for d in engagement.avg_percent_viewed_per_day}

    assert seconds[today] == 100  # summed
    assert percent[today] == 50  # averaged, and in percent, not a fraction


@pytest.mark.asyncio
async def test_engagement_rate_is_a_share_of_viewers_not_a_count_of_actions(
    session: AsyncSession,
):
    """It used to be (likes + comments) / views, which broke its own scale.

    One viewer who both liked and commented counted twice in the
    numerator, so three such viewers out of three reported 200 %.
    """
    owner = await make_user(session)
    channel = await make_channel(session, owner)
    video = await make_video(session, channel)

    both = await make_user(session)
    quiet = await make_user(session)
    for who in (both, quiet):
        await add_view(session, video, user=who, at=now())
    await add_reaction(session, video, both)
    await add_comment(session, video, both)

    engagement = await AnalyticsService(session).get_engagement(channel, Period.LAST_7)

    # One of two viewers did something, however many things they did.
    assert engagement.engagement_rate == 50.0


@pytest.mark.asyncio
async def test_engagement_rate_cannot_exceed_one_hundred(session: AsyncSession):
    """Every viewer engaging is 100 %, and engaging twice does not add more."""
    owner = await make_user(session)
    channel = await make_channel(session, owner)
    video = await make_video(session, channel)

    for _ in range(3):
        viewer = await make_user(session)
        await add_view(session, video, user=viewer, at=now())
        await add_reaction(session, video, viewer)
        await add_comment(session, video, viewer)

    engagement = await AnalyticsService(session).get_engagement(channel, Period.LAST_7)
    assert engagement.engagement_rate == 100.0


@pytest.mark.asyncio
async def test_engaging_without_a_view_in_the_period_does_not_count(
    session: AsyncSession,
):
    """The numerator is a subset of the denominator, which is the whole point.

    Someone who first watched before the period and comments during it used
    to land in the numerator while their view sat outside the denominator.
    """
    owner = await make_user(session)
    channel = await make_channel(session, owner)
    video = await make_video(session, channel)

    old_hand = await make_user(session)
    await add_view(session, video, user=old_hand, at=now() - timedelta(days=200))
    await add_comment(session, video, old_hand, at=now())

    newcomer = await make_user(session)
    await add_view(session, video, user=newcomer, at=now())

    engagement = await AnalyticsService(session).get_engagement(channel, Period.LAST_7)

    # One viewer this period, and they did nothing.
    assert engagement.engagement_rate == 0.0


@pytest.mark.asyncio
async def test_signed_out_viewers_lower_the_share(session: AsyncSession):
    """They cannot react or comment, so they can only ever dilute it."""
    owner = await make_user(session)
    channel = await make_channel(session, owner)
    video = await make_video(session, channel)

    engager = await make_user(session)
    await add_view(session, video, user=engager, at=now())
    await add_reaction(session, video, engager)
    await add_view(session, video, at=now(), viewer="anon:one")
    await add_view(session, video, at=now(), viewer="anon:two")
    await add_view(session, video, at=now(), viewer="fp:three")

    engagement = await AnalyticsService(session).get_engagement(channel, Period.LAST_7)
    assert engagement.engagement_rate == 25.0


@pytest.mark.asyncio
async def test_no_views_is_zero_not_an_error(session: AsyncSession):
    owner = await make_user(session)
    channel = await make_channel(session, owner)
    await make_video(session, channel)

    engagement = await AnalyticsService(session).get_engagement(channel, Period.LAST_7)
    assert engagement.engagement_rate == 0.0
