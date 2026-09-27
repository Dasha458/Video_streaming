import logging

from elasticsearch import AsyncElasticsearch, NotFoundError


async def index_video_in_es(video: dict, es: AsyncElasticsearch) -> None:
    """Quick metadata index after upload (runs inside the FastAPI process)."""

    await es.index(
        index="videos",
        id=str(video["id"]),
        document={
            "name": video["name"],
            "description": video.get("description"),
            "user_id": str(video.get("user_id")) if video.get("user_id") else None,
            "channel_id": (
                str(video.get("channel_id")) if video.get("channel_id") else None
            ),
            "category": video.get("category"),
            "views": video.get("views", 0),
            "privacy": video.get("privacy") or "public",
            "suggest_name": video["name"],
        },
    )


async def set_video_privacy_in_es(
    video_id: str, privacy: str, es: AsyncElasticsearch
) -> None:
    """Keep the indexed privacy in step with the database.

    Nothing touched the index when a video's privacy changed, so a video
    switched to private stayed searchable under its old public document.
    """
    try:
        await es.update(index="videos", id=str(video_id), doc={"privacy": privacy})
    except NotFoundError:
        logging.warning(f"Video {video_id} is not indexed; privacy not propagated.")


async def deindex_video_in_es(video_id: str, es: AsyncElasticsearch) -> None:
    """Safely delete it from Elasticsearch."""
    try:
        await es.delete(index="videos", id=str(video_id))
    except NotFoundError:
        logging.warning(
            f"Video {video_id} not found in Elasticsearch or already deleted."
        )
