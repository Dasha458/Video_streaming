import logging
import time
from pathlib import Path

from faststream.asgi import AsgiFastStream
from faststream.rabbit import RabbitBroker
from prometheus_client import CollectorRegistry, make_asgi_app

from src.config import get_rabbitmq_settings
from src.exceptions import (
    AppError,
    FFmpegExecutionError,
    FFmpegStartError,
    InvalidMediaError,
)
from src.messages import EncodeStatusMessage
from src.metrics import EncodeMetrics
from src.renditions import LADDER
from src.s3_client import get_s3_client
from src.services import (
    DOWNLOAD_NAME,
    build_download_file,
    check_liveness,
    cleanup_dirs,
    get_video_properties,
    has_gpu,
    prepare_dirs,
    stream_ffmpeg,
)

settings = get_rabbitmq_settings()
broker = RabbitBroker(settings.rabbitmq_url)
registry = CollectorRegistry()
# Without this the registry was empty: the endpoint answered, Prometheus
# called the target up, and not one measurement of the actual work existed.
metrics = EncodeMetrics(registry)
app = AsgiFastStream(
    broker,
    asgi_routes=[
        ("/api/metrics", make_asgi_app(registry)),
        ("/api/health/live", check_liveness),
    ],
)


async def publish_status(message: EncodeStatusMessage) -> None:
    await broker.publish(
        message.payload(),
        exchange="video.events",
        routing_key="video.encode.status",
    )


@broker.subscriber("video.encode")
async def encode_video(filename: str) -> None:
    s3_client = get_s3_client()
    video_id = Path(filename).stem

    metrics.started.inc()
    metrics.in_progress.inc()
    started_at = time.perf_counter()
    outcome = "failed"

    try:
        base_dir = await prepare_dirs(video_id)

        await publish_status(
            EncodeStatusMessage(video_id=video_id, status="processing")
        )

        video_url = await s3_client.generate_presigned_url(
            filename, bucket_name="videos", expiry=7200
        )
        properties = await get_video_properties(video_url)
        if not properties.fps:
            raise InvalidMediaError("could not determine FPS from video metadata")

        logging.info(
            "Detected video properties",
            extra={
                "video_id": video_id,
                "fps": properties.fps,
                "has_audio": properties.has_audio,
            },
        )

        try:
            await stream_ffmpeg(
                video_url,
                base_dir,
                int(round(properties.fps)),
                3,
                properties.has_audio,
            )
            metrics.encoder.labels(encoder="gpu" if await has_gpu() else "cpu").inc()
        except FFmpegExecutionError:
            logging.warning(
                "GPU encoding failed, retrying with CPU...",
                extra={"video_id": video_id},
            )
            cleanup_dirs(video_id)
            base_dir = await prepare_dirs(video_id)
            await stream_ffmpeg(
                video_url,
                base_dir,
                int(round(properties.fps)),
                3,
                properties.has_audio,
                force_cpu=True,
            )
            # The GPU path failed and the CPU one carried it: worth counting
            # separately, because a steady drift onto CPU is a capacity
            # problem long before it is an outage.
            metrics.encoder.labels(encoder="cpu").inc()

        # Built before the upload so it travels with everything else:
        # upload_dir sends the whole tree, so the file needs no special
        # handling at either end.
        try:
            await build_download_file(base_dir, properties.has_audio)
        except (FFmpegStartError, FFmpegExecutionError, OSError):
            # A video nobody can download is worse than nothing to
            # download; a video nobody can watch because the remux failed
            # would be far worse. The encode stands.
            logging.exception(
                "Could not build the downloadable file", extra={"video_id": video_id}
            )

        await s3_client.upload_dir(video_id, base_dir, bucket_name="videos")

        # Report exactly the renditions ffmpeg wrote, described by the same
        # ladder that drove the encode -- the numbers used to be retyped here
        # and disagreed with the encoder (854x360 @ 1200k vs 640x360 @ 800k).
        resolutions = [
            rendition.as_message(video_id)
            for rendition in LADDER
            if (base_dir / f"stream_{rendition.name}" / "playlist.m3u8").exists()
        ]

        await publish_status(
            EncodeStatusMessage(
                video_id=video_id,
                status="ready",
                resolutions=resolutions,
                video_path=f"minio/videos/{video_id}/master.m3u8",
            )
        )

        outcome = "ready"
        logging.info("Video encoding completed", extra={"video_id": video_id})

        await s3_client.delete_file(filename, bucket_name="videos")

    except Exception:
        # Every failure, not just our own AppError subclasses. A botocore
        # ClientError, an OSError or a ValueError out of the FPS parsing
        # used to escape this handler, so no "failed" status was ever
        # published and the video sat in "processing" for good -- which
        # the owner cannot even delete.
        logging.exception("Unhandled encoding error", extra={"video_id": video_id})
        try:
            await publish_status(
                EncodeStatusMessage(video_id=video_id, status="failed")
            )
        except Exception:
            # The broker is the one thing that cannot report its own
            # failure. Say so here rather than lose it.
            logging.exception(
                "Could not publish the failed status",
                extra={"video_id": video_id},
            )

    finally:
        metrics.in_progress.dec()
        metrics.finished.labels(outcome=outcome).inc()
        metrics.duration.observe(time.perf_counter() - started_at)

        # Never let cleanup replace the outcome above.
        try:
            cleanup_dirs(video_id)
            logging.debug("Cleanup completed", extra={"video_id": video_id})
        except AppError:
            logging.exception("Cleanup failed", extra={"video_id": video_id})


@broker.subscriber("video.download.build")
async def build_download_for_existing(video_id: str) -> None:
    """Build the downloadable file for a video that was encoded without one.

    Everything uploaded before the converter started producing
    download.mp4 has playlists and segments but no single file, so its
    owner sees "no downloadable file is available". Rather than re-encode
    from a source that no longer exists -- the converter deletes it once
    the encode succeeds -- this fetches the rendition already in storage
    and remuxes it, which is the same work the encode path now does at
    the end, and costs seconds.

    Driven by `python -m utils.backfill_downloads` on the backend side.
    """
    s3_client = get_s3_client()
    base_dir = await prepare_dirs(f"backfill-{video_id}")

    try:
        existing = await s3_client.list_keys(
            f"{video_id}/{DOWNLOAD_NAME}", bucket_name="videos"
        )
        if existing:
            logging.info(
                "Downloadable file already present, nothing to do",
                extra={"video_id": video_id},
            )
            return

        fetched = await s3_client.download_prefix(
            f"{video_id}/", base_dir, bucket_name="videos"
        )
        if not fetched:
            logging.warning(
                "Nothing in storage for this video; it cannot be rebuilt",
                extra={"video_id": video_id},
            )
            return

        # Audio is not recorded anywhere by the time a video is ready, and
        # the filter is a no-op on a stream that has none.
        built = await build_download_file(base_dir, has_audio=True)
        if built is None:
            logging.warning(
                "No rendition to rebuild from", extra={"video_id": video_id}
            )
            return

        with built.open("rb") as handle:
            await s3_client.upload_file(
                f"{video_id}/{DOWNLOAD_NAME}", handle, bucket_name="videos"
            )
        logging.info("Backfilled the downloadable file", extra={"video_id": video_id})

    except Exception:
        # One video failing must not stop the queue; the script reports
        # what it published and the logs say what happened to each.
        logging.exception(
            "Could not backfill the downloadable file", extra={"video_id": video_id}
        )
    finally:
        cleanup_dirs(f"backfill-{video_id}")
