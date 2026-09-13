from typing import List
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.errors.channels import (
    AlreadySubscribedError,
    CannotSubscribeOwnChannelError,
    ChannelAlreadyExistsError,
    ChannelNameTakenError,
    ChannelNotFoundError,
    NotSubscribedError,
)
from src.models import Channel, Notification, Subscription, Video
from src.schemas.channel import ChannelCreate, ChannelResponse, ChannelSubscriptionItem, ChannelUpdate


class ChannelService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_channel(self, user_id: UUID, data: ChannelCreate) -> ChannelResponse:
        # Check user doesn't already have a channel
        existing = await self.session.scalar(
            select(Channel).where(Channel.user_id == user_id)
        )
        if existing:
            raise ChannelAlreadyExistsError()

        # Check name is not taken
        name_taken = await self.session.scalar(
            select(Channel).where(Channel.name == data.name)
        )
        if name_taken:
            raise ChannelNameTakenError()

        channel = Channel(
            user_id=user_id,
            name=data.name,
            description=data.description,
        )
        self.session.add(channel)
        await self.session.commit()
        await self.session.refresh(channel)
        return self._to_response(channel, is_owner=True)

    async def get_my_channel(self, user_id: UUID) -> ChannelResponse | None:
        channel = await self.session.scalar(
            select(Channel).where(Channel.user_id == user_id)
        )
        if not channel:
            return None
        videos_count = await self._count_videos(channel.id)
        return self._to_response(channel, is_owner=True, videos_count=videos_count)

    async def get_by_name(self, channel_name: str, user_id: UUID | None) -> ChannelResponse:
        channel = await self.session.scalar(
            select(Channel).where(Channel.name == channel_name)
        )
        if not channel:
            raise ChannelNotFoundError()
        is_owner = user_id is not None and channel.user_id == user_id
        videos_count = await self._count_videos(channel.id)
        is_subscribed = False
        if user_id is not None and not is_owner:
            is_subscribed = await self.session.scalar(
                select(Subscription).where(
                    Subscription.subscriber_id == user_id,
                    Subscription.channel_id == channel.id,
                )
            ) is not None
        return self._to_response(channel, is_owner=is_owner, videos_count=videos_count, is_subscribed=is_subscribed)

    async def update_channel(self, user_id: UUID, data: ChannelUpdate) -> ChannelResponse:
        channel = await self.session.scalar(
            select(Channel).where(Channel.user_id == user_id)
        )
        if not channel:
            raise ChannelNotFoundError()

        if data.name is not None and data.name != channel.name:
            taken = await self.session.scalar(
                select(Channel).where(Channel.name == data.name)
            )
            if taken:
                raise ChannelNameTakenError()
            channel.name = data.name

        if data.description is not None:
            channel.description = data.description

        await self.session.commit()
        await self.session.refresh(channel)
        videos_count = await self._count_videos(channel.id)
        return self._to_response(channel, is_owner=True, videos_count=videos_count)

    async def subscribe(self, channel_name: str, user_id: UUID) -> None:
        channel = await self._get_channel_by_name(channel_name)

        if channel.user_id == user_id:
            raise CannotSubscribeOwnChannelError()

        existing = await self.session.scalar(
            select(Subscription).where(
                Subscription.subscriber_id == user_id,
                Subscription.channel_id == channel.id,
            )
        )
        if existing:
            raise AlreadySubscribedError()

        self.session.add(Subscription(subscriber_id=user_id, channel_id=channel.id))
        channel.subscribers_count += 1
        self.session.add(Notification(
            user_id=channel.user_id,
            content="Someone subscribed to your channel",
            link=f"/channel/{channel.name}",
            notification_type="new_subscriber",
        ))
        await self.session.commit()

    async def unsubscribe(self, channel_name: str, user_id: UUID) -> None:
        channel = await self._get_channel_by_name(channel_name)

        sub = await self.session.scalar(
            select(Subscription).where(
                Subscription.subscriber_id == user_id,
                Subscription.channel_id == channel.id,
            )
        )
        if not sub:
            raise NotSubscribedError()

        await self.session.delete(sub)
        channel.subscribers_count = max(0, channel.subscribers_count - 1)
        await self.session.commit()

    async def get_subscriptions(self, user_id: UUID) -> List[ChannelSubscriptionItem]:
        result = await self.session.execute(
            select(Channel)
            .join(Subscription, Subscription.channel_id == Channel.id)
            .where(Subscription.subscriber_id == user_id)
        )
        channels = result.scalars().all()

        items = []
        for ch in channels:
            vc = await self._count_videos(ch.id)
            items.append(
                ChannelSubscriptionItem(
                    channel_name=ch.name,
                    channel_avatar=ch.avatar_path,
                    subscribersCount=ch.subscribers_count,
                    videosCount=vc,
                    createdAt=ch.created_at.isoformat(),
                )
            )
        return items

    # --- Helpers ---

    async def _get_channel_by_name(self, name: str) -> Channel:
        channel = await self.session.scalar(
            select(Channel).where(Channel.name == name)
        )
        if not channel:
            raise ChannelNotFoundError()
        return channel

    async def _count_videos(self, channel_id: UUID) -> int:
        result = await self.session.scalar(
            select(func.count()).select_from(Video).where(Video.channel_id == channel_id)
        )
        return result or 0

    @staticmethod
    def _to_response(channel: Channel, is_owner: bool = False, videos_count: int = 0, is_subscribed: bool = False) -> ChannelResponse:
        return ChannelResponse(
            id=channel.id,
            name=channel.name,
            description=channel.description,
            subscribers_count=channel.subscribers_count,
            views_count=channel.views_count,
            avatar_path=channel.avatar_path,
            background_path=channel.background_path,
            created_at=channel.created_at,
            channel_avatar=channel.avatar_path or "",
            channel_name=channel.name,
            channelBanner=channel.background_path,
            subscribersCount=channel.subscribers_count,
            videosCount=videos_count,
            bio=channel.description,
            createdAt=channel.created_at.isoformat(),
            isOwner=is_owner,
            isSubscribed=is_subscribed,
        )
