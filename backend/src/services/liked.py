from typing import List, Tuple
from uuid import UUID, NAMESPACE_DNS, uuid5

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

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

        total = await self.session.scalar(
            select(func.count())
            .select_from(VideoReaction)
            .where(
                VideoReaction.user_id == user_id,
                VideoReaction.reaction_type_id == like_type.id,
            )
        ) or 0

        result = await self.session.execute(
            select(Video)
            .join(VideoReaction, VideoReaction.video_id == Video.id)
            .where(
                VideoReaction.user_id == user_id,
                VideoReaction.reaction_type_id == like_type.id,
            )
            .options(
                selectinload(Video.channel),
                selectinload(Video.privacy),
                selectinload(Video.resolutions),
            )
            .order_by(VideoReaction.created_at.desc())
            .offset((page - 1) * size)
            .limit(size)
        )
        videos = result.scalars().all()
        return [to_video_preview(v) for v in videos], total
