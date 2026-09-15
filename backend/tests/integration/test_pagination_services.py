"""
Real-Postgres tests for the four services stage 3 moved onto the shared
paginate_query() helper. liked.py is the interesting one -- it's the only
caller using the new `joins`/`count_from` parameters (selecting Video rows
through a VideoReaction join, counting VideoReaction rows rather than Video
rows), which a mocked session can't verify actually produces correct SQL.
"""

import uuid
from datetime import timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.models import Notification, VideoReaction, WatchHistory, WatchLater
from src.services.history import HistoryService
from src.services.liked import LikedService
from src.services.notifications import NotificationService
from src.services.watch_later import WatchLaterService
from tests.integration.conftest import (
    REACTION_DISLIKE_ID,
    REACTION_LIKE_ID,
    make_channel,
    make_user,
    make_video,
    now,
)

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_liked_lists_only_this_users_likes_not_dislikes_or_others(
    session: AsyncSession,
):
    owner = await make_user(session)
    channel = await make_channel(session, owner)
    liked_video = await make_video(session, channel, name="liked")
    disliked_video = await make_video(session, channel, name="disliked")

    me = await make_user(session)
    someone_else = await make_user(session)

    session.add_all(
        [
            VideoReaction(
                id=uuid.uuid4(),
                video_id=liked_video.id,
                user_id=me.id,
                reaction_type_id=REACTION_LIKE_ID,
            ),
            VideoReaction(
                id=uuid.uuid4(),
                video_id=disliked_video.id,
                user_id=me.id,
                reaction_type_id=REACTION_DISLIKE_ID,
            ),
            VideoReaction(
                id=uuid.uuid4(),
                video_id=liked_video.id,
                user_id=someone_else.id,
                reaction_type_id=REACTION_LIKE_ID,
            ),
        ]
    )
    await session.flush()

    items, total = await LikedService(session).list_liked(me.id, page=1, size=20)

    assert total == 1
    assert [v.title for v in items] == ["liked"]


@pytest.mark.asyncio
async def test_liked_count_matches_reaction_rows_not_distinct_videos(
    session: AsyncSession,
):
    """count_from=VideoReaction: the total should track reaction rows.
    Regression guard for the join/count_from parameters added in stage 3."""
    owner = await make_user(session)
    channel = await make_channel(session, owner)
    v1 = await make_video(session, channel, name="v1")
    v2 = await make_video(session, channel, name="v2")
    v3 = await make_video(session, channel, name="v3")
    me = await make_user(session)

    for v in (v1, v2, v3):
        session.add(
            VideoReaction(
                id=uuid.uuid4(),
                video_id=v.id,
                user_id=me.id,
                reaction_type_id=REACTION_LIKE_ID,
            )
        )
    await session.flush()

    items, total = await LikedService(session).list_liked(me.id, page=1, size=2)

    assert total == 3
    assert len(items) == 2  # page size respected


@pytest.mark.asyncio
async def test_liked_orders_by_reaction_time_not_video_creation_time(
    session: AsyncSession,
):
    owner = await make_user(session)
    channel = await make_channel(session, owner)
    older_video = await make_video(session, channel, name="older-video-liked-last")
    newer_video = await make_video(session, channel, name="newer-video-liked-first")
    me = await make_user(session)

    session.add_all(
        [
            VideoReaction(
                id=uuid.uuid4(),
                video_id=older_video.id,
                user_id=me.id,
                reaction_type_id=REACTION_LIKE_ID,
                created_at=now() - timedelta(hours=1),
            ),
            VideoReaction(
                id=uuid.uuid4(),
                video_id=newer_video.id,
                user_id=me.id,
                reaction_type_id=REACTION_LIKE_ID,
                created_at=now(),
            ),
        ]
    )
    await session.flush()

    items, _ = await LikedService(session).list_liked(me.id, page=1, size=20)

    assert [v.title for v in items] == [
        "newer-video-liked-first",
        "older-video-liked-last",
    ]


@pytest.mark.asyncio
async def test_history_paginates_and_scopes_to_the_user(session: AsyncSession):
    owner = await make_user(session)
    channel = await make_channel(session, owner)
    me = await make_user(session)
    other = await make_user(session)

    videos = [await make_video(session, channel, name=f"v{i}") for i in range(5)]
    for i, v in enumerate(videos):
        session.add(
            WatchHistory(
                id=uuid.uuid4(),
                user_id=me.id,
                video_id=v.id,
                last_watched_at=now() - timedelta(minutes=i),
            )
        )
    session.add(
        WatchHistory(
            id=uuid.uuid4(),
            user_id=other.id,
            video_id=videos[0].id,
            last_watched_at=now(),
        )
    )
    await session.flush()

    page1, total = await HistoryService(session).list(me.id, page=1, size=3)
    page2, _ = await HistoryService(session).list(me.id, page=2, size=3)

    assert total == 5
    assert len(page1) == 3
    assert len(page2) == 2
    assert {item.id for item in page1} & {item.id for item in page2} == set()


@pytest.mark.asyncio
async def test_watch_later_paginates_and_scopes_to_the_user(session: AsyncSession):
    owner = await make_user(session)
    channel = await make_channel(session, owner)
    me = await make_user(session)
    other = await make_user(session)
    video = await make_video(session, channel)

    session.add(WatchLater(id=uuid.uuid4(), user_id=me.id, video_id=video.id))
    session.add(WatchLater(id=uuid.uuid4(), user_id=other.id, video_id=video.id))
    await session.flush()

    items, total = await WatchLaterService(session).list(me.id, page=1, size=20)

    assert total == 1
    assert items[0].id == video.id


@pytest.mark.asyncio
async def test_notifications_paginate_and_report_unread_count_separately(
    session: AsyncSession,
):
    me = await make_user(session)
    other = await make_user(session)

    for i in range(4):
        session.add(
            Notification(
                id=uuid.uuid4(),
                user_id=me.id,
                content=f"n{i}",
                link="/x",
                is_read=(i < 2),
            )
        )
    session.add(
        Notification(
            id=uuid.uuid4(),
            user_id=other.id,
            content="not-mine",
            link="/x",
            is_read=False,
        )
    )
    await session.flush()

    page = await NotificationService(session).list(me.id, page=1, size=2)

    assert page.total == 4
    assert len(page.items) == 2
    # unread_count must reflect ALL of the user's notifications, not just this page.
    assert page.unread_count == 2
