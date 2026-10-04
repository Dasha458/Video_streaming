"""
Build the downloadable MP4 for videos that were encoded without one.

The Download button hands over a single file the converter prepares at
encode time. Everything encoded before that existed has playlists and
segments in storage but no such file, so its owner is told "no
downloadable file is available for this video" -- correctly, and
unhelpfully.

Re-encoding is not an option: the converter deletes the uploaded source
once an encode succeeds. What is still there is the finished rendition,
and remuxing it into an MP4 costs seconds and no quality. This publishes
one job per affected video to `video.download.build`; the converter does
the work, because that is where ffmpeg lives.

Dry run by default. Nothing is published without --run.

    python -m utils.backfill_downloads              # report only
    python -m utils.backfill_downloads --run        # publish the jobs
    python -m utils.backfill_downloads --run --yes  # no confirmation
"""

import argparse
import asyncio
import logging
from typing import List
from uuid import UUID

from sqlalchemy import select

from src.core.status_ids import STATUS_READY_ID
from src.infrastructure.database import async_session_maker
from src.infrastructure.s3_client import get_s3_client
from src.models import Video

QUEUE = "video.download.build"
DOWNLOAD_KEY = "download.mp4"

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger("backfill")


async def _ready_video_ids() -> List[UUID]:
    """Only ready videos: anything else has no rendition to remux."""
    async with async_session_maker() as session:
        rows = await session.execute(
            select(Video.id).where(Video.status_id == STATUS_READY_ID)
        )
    return [row[0] for row in rows]


async def _missing(video_ids: List[UUID]) -> List[UUID]:
    """The ones with no downloadable file in storage.

    Asked per video rather than by listing the whole bucket: the bucket
    holds every segment of every rendition, which is thousands of keys
    for a handful of videos.
    """
    client = get_s3_client()
    missing = []
    for video_id in video_ids:
        keys = await client.list_keys(
            f"{video_id}/{DOWNLOAD_KEY}", bucket_name="videos"
        )
        if not keys:
            missing.append(video_id)
    return missing


async def _publish(video_ids: List[UUID]) -> None:
    from src.infrastructure.messaging.client import shared_broker as broker

    await broker.connect()
    try:
        for video_id in video_ids:
            await broker.publish(str(video_id), queue=QUEUE)
            log.info("  queued %s", video_id)
    finally:
        await broker.close()


async def main(run: bool, assume_yes: bool) -> int:
    ready = await _ready_video_ids()
    log.info("Ready videos: %d", len(ready))

    missing = await _missing(ready)
    if not missing:
        log.info("Every ready video already has a downloadable file.")
        return 0

    log.info("Without a downloadable file: %d", len(missing))
    for video_id in missing[:20]:
        log.info("  %s", video_id)
    if len(missing) > 20:
        log.info("  ... and %d more", len(missing) - 20)

    if not run:
        log.info("\nDry run. Re-run with --run to queue the work.")
        return 0

    if not assume_yes:
        answer = input(f"\nQueue {len(missing)} rebuild jobs? [y/N] ").strip().lower()
        if answer != "y":
            log.info("Nothing queued.")
            return 1

    await _publish(missing)
    log.info(
        "\nQueued %d jobs. The converter logs each one; re-run this script to "
        "see what is left.",
        len(missing),
    )
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--run", action="store_true", help="publish the jobs (default: report only)"
    )
    parser.add_argument(
        "--yes", action="store_true", help="skip the confirmation prompt"
    )
    args = parser.parse_args()
    raise SystemExit(asyncio.run(main(args.run, args.yes)))
