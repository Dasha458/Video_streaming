from typing import List, Tuple
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.core.pagination import paginate_query
from src.models import ReactionType, Video, VideoReaction
from src.schemas.video import VideoPreview, to_video_preview


class LikedService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def list_liked(self, user_id: UUID, page: int, size: int) -> Tuple[List[VideoPreview], int]:
        like_type = await self.session.scalar(
            select(ReactionType).where(ReactionType.name == "like")
        )
        if not like_type:
            return [], 0

        return await paginate_query(
            self.session,
            Video,
            page=page,
            size=size,
            filters=[
                VideoReaction.user_id == user_id,
                VideoReaction.reaction_type_id == like_type.id,
            ],
            count_from=VideoReaction,
            joins=[(VideoReaction, VideoReaction.video_id == Video.id)],
            order_by=VideoReaction.created_at.desc(),
            preload=[
                selectinload(Video.channel),
                selectinload(Video.privacy),
                selectinload(Video.resolutions),
            ],
            mapper=to_video_preview,
        )
