import logging
from pathlib import Path

from faststream.asgi import AsgiFastStream
from faststream.rabbit import RabbitBroker
from prometheus_client import CollectorRegistry, make_asgi_app

from src.config import get_rabbitmq_settings
from src.exceptions import AppError, FFmpegExecutionError, InvalidMediaError
from src.renditions import LADDER
from src.s3_client import get_s3_client
from src.services import (
    check_liveness,
    cleanup_dirs,
    get_video_properties,
    prepare_dirs,
    stream_ffmpeg,
)

settings = get_rabbitmq_settings()
broker = RabbitBroker(settings.rabbitmq_url)
registry = CollectorRegistry()
app = AsgiFastStream(
    broker,
    asgi_routes=[
        ("/api/metrics", make_asgi_app(registry)),
        ("/api/health/live", check_liveness),
    ],
)


@broker.subscriber("video.encode")
async def encode_video(filename: str) -> None:
    s3_client = get_s3_client()
    video_id = Path(filename).stem

    try:
        base_dir = await prepare_dirs(video_id)

        await broker.publish(
            {"video_id": video_id, "status": "processing"},
            exchange="video.events",
            routing_key="video.encode.status",
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

        await s3_client.upload_dir(video_id, base_dir, bucket_name="videos")

        # Report exactly the renditions ffmpeg wrote, described by the same
        # ladder that drove the encode -- the numbers used to be retyped here
        # and disagreed with the encoder (854x360 @ 1200k vs 640x360 @ 800k).
        resolutions = [
            rendition.as_message(video_id)
            for rendition in LADDER
            if (base_dir / f"stream_{rendition.name}" / "playlist.m3u8").exists()
        ]

        await broker.publish(
            {
                "video_id": video_id,
                "status": "ready",
                "resolutions": resolutions,
                "video_path": f"minio/videos/{video_id}/master.m3u8",
            },
            exchange="video.events",
            routing_key="video.encode.status",
        )

        logging.info("Video encoding completed", extra={"video_id": video_id})

        await s3_client.delete_file(filename, bucket_name="videos")

    except AppError:
        await broker.publish(
            {"video_id": video_id, "status": "failed"},
            exchange="video.events",
            routing_key="video.encode.status",
        )

        logging.exception(
            "Unhandled encoding error",
            extra={"video_id": video_id},
        )

    finally:
        cleanup_dirs(video_id)
        logging.debug("Cleanup completed", extra={"video_id": video_id})
