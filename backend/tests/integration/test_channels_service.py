"""
Real-Postgres tests for the shape a channel is returned in.

Nothing covered it, which is how it came to carry eighteen fields for six
pieces of information: every value appeared twice, under snake_case and
camelCase, filled from the same source. The frontend read
`subscribersCount ?? subscribers_count ?? 0` because nothing said which
would arrive.
"""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.schemas.channel import ChannelResponse, ChannelSubscriptionItem
from src.services.channels import ChannelService
from tests.integration.conftest import make_channel, make_user, make_video

pytestmark = pytest.mark.integration

#: Everything a channel response is allowed to contain.
EXPECTED_FIELDS = {
    "id",
    "name",
    "description",
    "subscribers_count",
    "views_count",
    "videos_count",
    "avatar_path",
    "background_path",
    "created_at",
    "is_owner",
    "is_subscribed",
}


def test_no_value_is_declared_twice():
    """The guard. A second name for the same value is how this started."""
    assert set(ChannelResponse.model_fields) == EXPECTED_FIELDS

    # Each of these pairs used to be present together.
    for gone in (
        "channel_name",
        "channel_avatar",
        "channelBanner",
        "subscribersCount",
        "videosCount",
        "bio",
        "createdAt",
        "isOwner",
        "isSubscribed",
    ):
        assert gone not in ChannelResponse.model_fields, gone


def test_the_subscriptions_item_uses_the_same_names():
    assert set(ChannelSubscriptionItem.model_fields) == {
        "name",
        "avatar_path",
        "subscribers_count",
        "videos_count",
        "created_at",
    }


@pytest.mark.asyncio
async def test_a_channel_is_returned_with_its_real_values(session: AsyncSession):
    owner = await make_user(session)
    channel = await make_channel(session, owner)
    channel.description = "what this channel is about"
    channel.avatar_path = "/minio/video-thumbnails/avatar.jpg"
    await session.flush()
    await make_video(session, channel)
    await make_video(session, channel)

    response = await ChannelService(session).get_by_name(channel.name, owner.id)

    assert response.name == channel.name
    assert response.description == "what this channel is about"
    assert response.avatar_path == "/minio/video-thumbnails/avatar.jpg"
    assert response.videos_count == 2
    assert response.is_owner is True
    assert response.is_subscribed is False


@pytest.mark.asyncio
async def test_a_stranger_is_not_the_owner(session: AsyncSession):
    owner = await make_user(session)
    stranger = await make_user(session)
    channel = await make_channel(session, owner)

    response = await ChannelService(session).get_by_name(channel.name, stranger.id)
    assert response.is_owner is False
    assert response.is_subscribed is False


@pytest.mark.asyncio
async def test_subscribing_shows_up_in_both_places(session: AsyncSession):
    owner = await make_user(session)
    viewer = await make_user(session)
    channel = await make_channel(session, owner)
    await make_video(session, channel)

    service = ChannelService(session)
    await service.subscribe(channel.name, viewer.id)

    response = await service.get_by_name(channel.name, viewer.id)
    assert response.is_subscribed is True
    assert response.subscribers_count == 1

    items = await service.get_subscriptions(viewer.id)
    assert [i.name for i in items] == [channel.name]
    assert items[0].subscribers_count == 1
    assert items[0].videos_count == 1
