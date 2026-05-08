import uuid
from typing import Type

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute

from src.errors.reactions import InvalidReactionTypeError
from src.models import CommentReaction, ReactionType
from src.models.video_reactions import VideoReaction


async def toggle_reaction(
    session: AsyncSession,
    user_id: uuid.UUID,
    target_model: Type[VideoReaction] | Type[CommentReaction],
    target_field: InstrumentedAttribute[
        uuid.UUID
    ],  # target_model.video_id or target_model.comment_id
    target_id: uuid.UUID,
    reaction_name: str,  # e.g. "like" or "love"
) -> dict[str, int]:
    """Toggle reaction for a user on a video or comment."""

    reaction_type_id = await session.scalar(
        select(ReactionType.id).where(ReactionType.name == reaction_name)
    )
    if not reaction_type_id:
        raise InvalidReactionTypeError(reaction_name)

    # Check if the user already reacted
    stmt = select(target_model).where(
        target_model.user_id == user_id,
        target_field == target_id,
    )
    existing = await session.scalar(stmt)

    if existing is not None:
        if existing.reaction_type_id == reaction_type_id:
            # Same reaction type → toggle off (delete)
            await session.delete(existing)
        else:
            # Different reaction type → switch
            existing.reaction_type_id = reaction_type_id
    else:
        # No existing reaction → create
        session.add(
            target_model(
                user_id=user_id,
                reaction_type_id=reaction_type_id,
                **{target_field.key: target_id},
            )
        )

    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise

    # Count all reactions for this target
    result = await session.execute(
        select(ReactionType.name, func.count())
        .join(target_model, target_model.reaction_type_id == ReactionType.id)
        .where(target_field == target_id)
        .group_by(ReactionType.name)
    )
    counts = {name: count for name, count in result.all()}
    return counts
