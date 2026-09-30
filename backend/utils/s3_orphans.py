"""
Find (and optionally remove) objects in storage that no longer belong to a
video.

Why this exists: until 2026-09-29 deleting a video removed its database
row and left every byte behind -- it asked for the key `str(video.id)`
while the original upload is stored as `<id><suffix>`, and it never
touched the transcoded tree under `<id>/`. Anything deleted before that
fix is still sitting in the bucket with nothing pointing at it.

An object is an orphan when the video it belongs to is not in the
database:

  videos/<id>.<ext>      the uploaded source
  videos/<id>/...        the transcoded playlists and segments
  video-thumbnails/<f>   matched against videos.thumbnail_path

Versioning is enabled on these buckets, so a plain delete only writes a
delete marker and the bytes stay as a noncurrent version. This removes
every version of an orphan, which is the only way the space actually
comes back.

Dry run by default. Nothing is deleted without --delete.

    python -m utils.s3_orphans                 # report only
    python -m utils.s3_orphans --delete        # remove them
    python -m utils.s3_orphans --delete --yes  # no confirmation prompt
"""

import argparse
import asyncio
import logging
from typing import Any, Dict, List, Set, Tuple

from sqlalchemy import select

from src.infrastructure.database import async_session_maker
from src.infrastructure.s3_client import get_s3_client
from src.models import Video

BUCKETS = ("videos", "video-thumbnails")
#: S3 accepts up to 1000 keys per delete_objects call.
DELETE_BATCH = 900


async def _live_references() -> Tuple[Set[str], Set[str]]:
    """The video ids and thumbnail filenames the database still knows about."""
    async with async_session_maker() as session:
        rows = (await session.execute(select(Video.id, Video.thumbnail_path))).all()
    ids = {str(row[0]) for row in rows}
    thumbs = {(row[1] or "").rsplit("/", 1)[-1] for row in rows if row[1]}
    return ids, thumbs


def _owner_of(bucket: str, key: str) -> str:
    """Which video a key belongs to, as the key itself spells it."""
    if bucket != "videos":
        return key
    # "<id>/stream_360p/seg_000.ts" -> "<id>";  "<id>.mp4" -> "<id>"
    return key.split("/", 1)[0].rsplit(".", 1)[0]


def _is_orphan(bucket: str, key: str, ids: Set[str], thumbs: Set[str]) -> bool:
    if bucket == "videos":
        return _owner_of(bucket, key) not in ids
    return key not in thumbs


async def _scan(
    client: Any, bucket: str, ids: Set[str], thumbs: Set[str]
) -> Tuple[List[Dict[str, str]], int, int]:
    """Every version of every orphan in one bucket, plus the bytes involved."""
    orphans: List[Dict[str, str]] = []
    orphan_bytes = 0
    kept = 0

    paginator = client.get_paginator("list_object_versions")
    async for page in paginator.paginate(Bucket=bucket):
        # Delete markers count too: they are what a plain delete left behind,
        # and they keep the noncurrent versions reachable.
        for kind in ("Versions", "DeleteMarkers"):
            for obj in page.get(kind, []):
                key = obj["Key"]
                if _is_orphan(bucket, key, ids, thumbs):
                    orphans.append({"Key": key, "VersionId": obj["VersionId"]})
                    orphan_bytes += obj.get("Size", 0)
                else:
                    kept += 1
    return orphans, orphan_bytes, kept


async def run(delete: bool, assume_yes: bool) -> int:
    ids, thumbs = await _live_references()
    print(f"database: {len(ids)} videos, {len(thumbs)} thumbnails")

    client = get_s3_client()
    total_versions = 0
    total_bytes = 0
    plan: List[Tuple[str, List[Dict[str, str]]]] = []

    async with client._get_client() as s3:
        for bucket in BUCKETS:
            orphans, orphan_bytes, kept = await _scan(s3, bucket, ids, thumbs)
            print(
                f"{bucket}: {len(orphans)} orphaned versions "
                f"({orphan_bytes / 1024 / 1024:.2f} MB), {kept} kept"
            )
            for entry in sorted(o["Key"] for o in orphans)[:20]:
                print(f"    {entry}")
            if len(orphans) > 20:
                print(f"    ... and {len(orphans) - 20} more")

            total_versions += len(orphans)
            total_bytes += orphan_bytes
            plan.append((bucket, orphans))

        if not total_versions:
            print("nothing to remove")
            return 0

        print(
            f"\ntotal: {total_versions} versions, "
            f"{total_bytes / 1024 / 1024:.2f} MB"
        )
        if not delete:
            print("dry run -- pass --delete to remove them")
            return 0

        if not assume_yes:
            answer = input("remove every version listed above? [y/N] ").strip()
            if answer.lower() not in ("y", "yes"):
                print("cancelled")
                return 1

        removed = 0
        for bucket, orphans in plan:
            for start in range(0, len(orphans), DELETE_BATCH):
                batch = orphans[start : start + DELETE_BATCH]
                await s3.delete_objects(
                    Bucket=bucket, Delete={"Objects": batch, "Quiet": True}
                )
                removed += len(batch)
        print(f"removed {removed} versions, {total_bytes / 1024 / 1024:.2f} MB")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--delete",
        action="store_true",
        help="actually remove what the report lists (default: report only)",
    )
    parser.add_argument(
        "--yes", action="store_true", help="skip the confirmation prompt"
    )
    args = parser.parse_args()

    logging.disable(logging.INFO)
    raise SystemExit(asyncio.run(run(delete=args.delete, assume_yes=args.yes)))


if __name__ == "__main__":
    main()
