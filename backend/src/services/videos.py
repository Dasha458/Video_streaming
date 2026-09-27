import uuid as _uuid
from typing import TYPE_CHECKING, Any, List, Tuple, cast, get_args
from uuid import NAMESPACE_DNS, UUID, uuid5

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.core.pagination import paginate_query
from src.core.status_ids import PRIVACY_PUBLIC_ID, STATUS_READY_ID
from src.errors.videos import (
    InvalidPrivacyError,
    VideoNotFoundError,
    VideoPrivacyUpdateForbidden,
)
from src.models import Category, Channel, PrivacyStatus, Video, VideoReaction, VideoView
from src.models.watch_history import WatchHistory
from src.schemas.video import (
    VideoCategory,
    VideoPlayback,
    VideoPreview,
    map_video_to_playback,
    to_video_preview,
)
from src.services.reactions import toggle_reaction

if TYPE_CHECKING:
    from sqlalchemy import CursorResult


class VideoService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_playback(
        self,
        video_id: UUID,
        user_id: UUID | None,
        source_type: str | None = None,
    ) -> VideoPlayback:
        video = await self._get_video_with_details(video_id)

        # list_videos() filters to public+ready, but fetching one video by id
        # used to return anything at all -- a private video's metadata (and,
        # once encoded, its master playlist URL) was served to anyone holding
        # the id, anonymous included. Only the owner may see a video that is
        # not public and ready. Raising "not found" rather than "forbidden"
        # keeps the endpoint from confirming that the id exists.
        is_public = video.privacy_id == PRIVACY_PUBLIC_ID
        is_ready = video.status_id == STATUS_READY_ID
        if not (is_public and is_ready):
            owner_id = video.channel.user_id if video.channel else None
            if user_id is None or owner_id != user_id:
                raise VideoNotFoundError()

        await self._record_view(video.id, user_id, source_type=source_type)

        resolutions = [f"{r.height}p" for r in video.resolutions]
        return map_video_to_playback(video, resolutions)

    async def list_videos(
        self,
        page: int,
        size: int,
        category: str | None = None,
        channel_name: str | None = None,
    ) -> Tuple[List[VideoPreview], int]:
        """
        Retrieves public, ready videos. Optionally filters by category and/or channel name.
        """
        filters = [
            Video.privacy_id == PRIVACY_PUBLIC_ID,
            Video.status_id == STATUS_READY_ID,
        ]

        if category:
            category_id = uuid5(NAMESPACE_DNS, f"video_category:{category.lower()}")
            filters.append(Video.category_id == category_id)

        if channel_name:
            channel = await self.session.scalar(
                select(Channel).where(Channel.name == channel_name)
            )
            if channel:
                filters.append(Video.channel_id == channel.id)
            else:
                # Channel not found — return empty result
                return [], 0

        preload = [
            selectinload(Video.channel),
            selectinload(Video.privacy),
            selectinload(Video.resolutions),
        ]

        return await paginate_query(
            session=self.session,
            model=Video,
            page=page,
            size=size,
            filters=filters,
            preload=preload,
            order_by=Video.created_at.desc(),
            mapper=to_video_preview,
        )

    async def list_categories(self, plain: bool) -> List[str]:
        if plain:
            return list(get_args(VideoCategory))
        result = await self.session.execute(
            select(Category.name)
            .join(Video, Category.id == Video.category_id)
            .distinct()
            .order_by(Category.name)
        )
        return [str(name) for name in result.scalars().all()]

    async def react(self, video_id: UUID, user_id: UUID, reaction_name: str) -> dict:
        return await toggle_reaction(
            session=self.session,
            user_id=user_id,
            target_model=VideoReaction,
            target_field=VideoReaction.video_id,
            target_id=video_id,
            reaction_name=reaction_name,
            parent_model=Video,
        )

    async def update_privacy(
        self, video_id: UUID, user_id: UUID, privacy_name: str
    ) -> Tuple[str, str]:
        # Validate Privacy Level
        privacy = await self.session.scalar(
            select(PrivacyStatus).where(PrivacyStatus.name == privacy_name)
        )
        if not privacy:
            raise InvalidPrivacyError(privacy_name)

        # Validate Ownership and Existence
        video = await self.session.scalar(
            select(Video)
            .join(Channel)
            .options(selectinload(Video.privacy))
            .where(Video.id == video_id, Channel.user_id == user_id)
        )
        if not video:
            raise VideoPrivacyUpdateForbidden()

        old_privacy = video.privacy.name if video.privacy else "unknown"

        # Update
        video.privacy_id = privacy.id
        await self.session.commit()

        return old_privacy, privacy.name

    async def filter_public_ready_ids(self, video_ids: list[UUID]) -> set[UUID]:
        """Of the given ids, those that are public and finished encoding.

        The search index is a cache and can lag reality -- a video made
        private after it was indexed, or indexed before the index carried a
        privacy field at all. The database is the authority, so search
        results are checked against it before they leave the server.
        """
        if not video_ids:
            return set()
        rows = await self.session.execute(
            select(Video.id).where(
                Video.id.in_(video_ids),
                Video.privacy_id == PRIVACY_PUBLIC_ID,
                Video.status_id == STATUS_READY_ID,
            )
        )
        return set(rows.scalars().all())

    # --- Internal Helpers ---

    async def _get_video_with_details(self, video_id: UUID) -> Video:
        result = await self.session.execute(
            select(Video)
            .options(
                selectinload(Video.channel),
                selectinload(Video.privacy),
                selectinload(Video.resolutions),
            )
            .where(Video.id == video_id)
        )
        video = result.scalar_one_or_none()
        if not video:
            raise VideoNotFoundError()
        return video

    async def _record_view(
        self,
        video_id: UUID,
        user_id: UUID | None,
        source_type: str | None = None,
    ) -> None:
        """Record a view and, for signed-in users, refresh watch history.

        Anonymous views used to be dropped entirely -- the caller only
        reached this method ``if user_id``. That contradicted the schema,
        which makes ``user_id`` nullable and scopes the unique index to
        ``WHERE user_id IS NOT NULL`` precisely so anonymous rows can exist.
        The effect was that traffic sources, real-time and audience panels
        never saw a single signed-out viewer.

        For a signed-in user the partial unique index still allows one row
        per (video, user). Leaning on ON CONFLICT instead of a preceding
        SELECT also closes the race where two simultaneous first views both
        passed the existence check and the second raised an IntegrityError.
        """
        source = (source_type or "unknown")[:32]

        insert_view = (
            pg_insert(VideoView)
            .values(
                id=_uuid.uuid4(),
                video_id=video_id,
                user_id=user_id,
                source_type=source,
            )
            .on_conflict_do_nothing(
                index_elements=["video_id", "user_id"],
                index_where=VideoView.user_id.isnot(None),
            )
        )
        # rowcount lives on CursorResult; execute() is typed as Result.
        result = cast("CursorResult[Any]", await self.session.execute(insert_view))

        if result.rowcount:
            await self.session.execute(
                update(Video)
                .where(Video.id == video_id)
                .values(views_count=Video.views_count + 1)
            )
        elif source != "unknown":
            # The row survives from an earlier visit. Fill in the traffic
            # source if it was never learned -- it used to be written only
            # on the very first view and never afterwards, so every row
            # stayed "unknown" for as long as the player sent nothing.
            await self.session.execute(
                update(VideoView)
                .where(
                    VideoView.video_id == video_id,
                    VideoView.user_id == user_id,
                    (VideoView.source_type.is_(None))
                    | (VideoView.source_type == "unknown"),
                )
                .values(source_type=source)
            )

        if user_id is not None:
            # Upsert watch history (create or refresh timestamp on re-watch)
            await self.session.execute(
                pg_insert(WatchHistory)
                .values(
                    id=_uuid.uuid4(),
                    user_id=user_id,
                    video_id=video_id,
                    last_watched_at=func.now(),
                )
                .on_conflict_do_update(
                    index_elements=["user_id", "video_id"],
                    set_={"last_watched_at": func.now()},
                )
            )

        await self.session.commit()
