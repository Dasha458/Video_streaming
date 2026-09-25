import asyncio
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from uuid import NAMESPACE_DNS, UUID, uuid5

import aiofiles
import httpx
from fastapi import UploadFile
from fastapi_users.password import PasswordHelper
from sqlalchemy.dialects.postgresql import insert
from starlette.datastructures import Headers

from src.infrastructure import get_rabbit_broker
from src.infrastructure.database import async_session_maker
from src.infrastructure.s3_client import get_s3_client
from src.models import (
    Category,
    Channel,
    PrivacyStatus,
    ReactionType,
    Role,
    User,
    UserStatus,
    VideoStatus,
)
from src.models.video import Video
from src.services.files import FileService

_password_helper = PasswordHelper()
# All seed users share this password. Change before deploying to production.
SEED_PASSWORD = "Test1234!"
_SEED_HASHED_PASSWORD = _password_helper.hash(SEED_PASSWORD)

SEED_FILE = Path(__file__).parent / "initial_data.json"


def deterministic_uuid(scope: str, name: str) -> UUID:
    """Generate deterministic UUID5 using a scope prefix."""
    return uuid5(NAMESPACE_DNS, f"{scope}:{name.lower()}")


USER_ID = deterministic_uuid("user", "John Doe")

# ── Seed users ────────────────────────────────────────────────────────────────
SEED_USERS = [
    {
        "name": "John Doe",
        "email": "john@example.com",
        "role": "admin",
    },
    {
        "name": "Alice Johnson",
        "email": "alice@example.com",
        "role": "user",
    },
    {
        "name": "Bob Smith",
        "email": "bob@example.com",
        "role": "user",
    },
    {
        "name": "Carol White",
        "email": "carol@example.com",
        "role": "user",
    },
    {
        "name": "David Brown",
        "email": "david@example.com",
        "role": "user",
    },
]

# ── Seed videos (3 per channel, 5 channels = 15 total) ───────────────────────
SEED_VIDEOS = {
    "John Doe": [
        {
            "name": "Building an HLS Streaming Server",
            "description": "Learn how to set up your own HLS video streaming server from scratch using NGINX and FFmpeg.",
            "category": "technology",
            "privacy": "public",
        },
        {
            "name": "Docker Compose for Beginners",
            "description": "A step-by-step guide to containerizing multi-service applications with Docker Compose.",
            "category": "technology",
            "privacy": "public",
        },
        {
            "name": "FastAPI Authentication Deep Dive",
            "description": "Implementing JWT authentication, OAuth2, and role-based access control in FastAPI.",
            "category": "education",
            "privacy": "public",
        },
    ],
    "Alice Johnson": [
        {
            "name": "Morning Yoga for Beginners",
            "description": "Start your day with this gentle 20-minute yoga flow designed for complete beginners.",
            "category": "health & fitness",
            "privacy": "public",
        },
        {
            "name": "Healthy Meal Prep: 5 Lunches in 30 Minutes",
            "description": "Efficient meal prep routine for busy weekdays — nutritious, delicious, and budget-friendly.",
            "category": "food & cooking",
            "privacy": "public",
        },
        {
            "name": "Mindfulness Meditation: 10-Minute Daily Practice",
            "description": "A guided meditation session to reduce stress and improve focus.",
            "category": "health & fitness",
            "privacy": "public",
        },
    ],
    "Bob Smith": [
        {
            "name": "Top 10 Gaming Moments of 2024",
            "description": "The most epic, funny, and memorable gaming clips from this year's biggest titles.",
            "category": "gaming",
            "privacy": "public",
        },
        {
            "name": "Elden Ring: Complete Beginner's Guide",
            "description": "Everything you need to know before starting Elden Ring — builds, bosses, and exploration tips.",
            "category": "gaming",
            "privacy": "public",
        },
        {
            "name": "Building a Gaming PC on a Budget",
            "description": "How to assemble a capable gaming rig for under $600 in 2024.",
            "category": "technology",
            "privacy": "public",
        },
    ],
    "Carol White": [
        {
            "name": "Exploring Tokyo: Hidden Gems",
            "description": "Off-the-beaten-path spots in Tokyo that most tourists never discover.",
            "category": "travel",
            "privacy": "public",
        },
        {
            "name": "Solo Travel Safety Tips for Women",
            "description": "Practical advice and strategies for safe and enjoyable solo travel as a woman.",
            "category": "travel",
            "privacy": "public",
        },
        {
            "name": "Budget Travel: Europe in 30 Days",
            "description": "How to explore 10 European countries in a month for under $2000.",
            "category": "travel",
            "privacy": "public",
        },
    ],
    "David Brown": [
        {
            "name": "Stand-up Comedy Special: Daily Life",
            "description": "A hilarious take on everyday situations that everyone can relate to.",
            "category": "comedy",
            "privacy": "public",
        },
        {
            "name": "Funniest Animal Videos Compilation",
            "description": "30 minutes of the most entertaining animal moments caught on camera.",
            "category": "animals & nature",
            "privacy": "public",
        },
        {
            "name": "Classic Movie Scenes Reimagined",
            "description": "Amateur recreations of iconic movie scenes with unexpected twists.",
            "category": "entertainment",
            "privacy": "public",
        },
    ],
}


def parse_date(date_string: str) -> datetime:
    """Safely converts an ISO string into a Python datetime object."""
    return datetime.fromisoformat(date_string)


async def seed_videos_via_service(session, user_id: UUID) -> None:
    """Seeds the first video through the actual business logic pipeline (upload + broker)."""
    video_path = "./assets/1280_placeholder.mp4"
    thumb_path = "./assets/thumbnail.png"

    if not os.path.exists(video_path) or not os.path.exists(thumb_path):
        logging.warning("Assets missing. Skipping FileService video seeding.")
        return

    logging.info("Initializing infrastructure clients for FileService...")

    s3_client = get_s3_client()
    broker = await get_rabbit_broker()
    await broker.connect()

    file_service = FileService(session=session, s3_client=s3_client, broker=broker)

    logging.info("Pushing video through business logic pipeline...")

    with open(video_path, "rb") as v_file, open(thumb_path, "rb") as t_file:
        video_upload = UploadFile(
            filename="1280_placeholder.mp4",
            file=v_file,
            headers=Headers({"content-type": "video/mp4"}),
        )
        thumb_upload = UploadFile(
            filename="thumbnail.png",
            file=t_file,
            headers=Headers({"content-type": "image/png"}),
        )

        try:
            response = await file_service.upload_video(
                video=video_upload,
                thumbnail=thumb_upload,
                name="Building an HLS Streaming Server",
                description="This video was seeded via the backend business logic pipeline!",
                privacy="public",
                category="Education",
                user_id=user_id,
            )
            logging.info(f"Successfully queued video! Response: {response}")
        except Exception as e:
            logging.error(f"Failed to seed video via FileService: {e}")
        finally:
            await broker.close()


async def seed_users_channels_videos(session) -> None:
    """Insert seed users, channels, and 15 videos directly into the DB (status=ready)."""

    status_id = deterministic_uuid("video_status", "ready")
    privacy_id = deterministic_uuid("privacy_status", "public")
    active_status_id = deterministic_uuid("user_status", "active")
    user_role_id = deterministic_uuid("user_role", "user")
    admin_role_id = deterministic_uuid("user_role", "admin")

    created_at_base = datetime(2024, 1, 1, tzinfo=timezone.utc)

    for idx, u in enumerate(SEED_USERS):
        user_id = deterministic_uuid("user", u["name"])
        role_id = admin_role_id if u["role"] == "admin" else user_role_id
        username = u["name"].lower().replace(" ", "_")

        # ── User ──────────────────────────────────────────────────────────────
        await session.execute(
            insert(User)
            .values(
                [
                    {
                        "id": user_id,
                        "username": username,
                        "email": u["email"],
                        "hashed_password": _SEED_HASHED_PASSWORD,
                        "is_active": True,
                        "is_superuser": u["role"] == "admin",
                        "is_verified": True,
                        "status_id": active_status_id,
                        "role_id": role_id,
                        "created_at": created_at_base,
                    }
                ]
            )
            .on_conflict_do_nothing(index_elements=["username"])
        )

        channel_id = deterministic_uuid("channel", u["name"])
        channel_name = f"{u['name'].split()[0].lower()}_channel"

        # ── Channel ───────────────────────────────────────────────────────────
        await session.execute(
            insert(Channel)
            .values(
                [
                    {
                        "id": channel_id,
                        "name": channel_name,
                        "user_id": user_id,
                        "subscribers_count": idx * 137,
                        "description": f"Official channel of {u['name']}.",
                        "views_count": idx * 2500,
                        "avatar_path": f"/minio/avatars/{channel_id}.png",
                        "background_path": f"/minio/backgrounds/{channel_id}.png",
                        "created_at": created_at_base,
                    }
                ]
            )
            .on_conflict_do_nothing(index_elements=["id"])
        )

        # ── Videos ────────────────────────────────────────────────────────────
        for v_idx, v in enumerate(SEED_VIDEOS[u["name"]]):
            video_id = deterministic_uuid("video", f"{u['name']}:{v['name']}")
            category_id = deterministic_uuid("video_category", v["category"])
            fake_hash = f"seed_{username}_{v_idx:02d}_{'x' * 16}"

            await session.execute(
                insert(Video)
                .values(
                    [
                        {
                            "id": video_id,
                            "name": v["name"],
                            "description": v["description"],
                            "size": 60_000_000 + v_idx * 5_000_000,
                            "hash": fake_hash,
                            "video_path": f"/minio/videos/{video_id}/master.m3u8",
                            "thumbnail_path": None,
                            "channel_id": channel_id,
                            "privacy_id": privacy_id,
                            "category_id": category_id,
                            "status_id": status_id,
                            "views_count": (idx + v_idx) * 312,
                            "likes_count": (idx + v_idx) * 47,
                            "dislikes_count": v_idx * 3,
                            "created_at": created_at_base,
                            "updated_at": created_at_base,
                        }
                    ]
                )
                .on_conflict_do_nothing(index_elements=["hash"])
            )

    await session.commit()
    logging.info("Seeded 5 users, 5 channels, 15 videos.")


async def _fetch_media_files() -> None:
    """Download assets from the specified URL."""
    files_to_download = [
        {
            "url": "https://placeholdervideo.dev/1280x720",
            "filename": "1280_placeholder.mp4",
        },
        {
            "url": "https://placeholdervideo.dev/1920x1080",
            "filename": "1920_placeholder.mp4",
        },
        {
            "url": "https://placehold.co/600x400/000000/FFFFFF.png",
            "filename": "thumbnail.png",
        },
    ]

    download_folder = "./assets"
    os.makedirs(download_folder, exist_ok=True)

    async with httpx.AsyncClient() as client:
        for file in files_to_download:
            local_path = os.path.join(download_folder, file["filename"])
            print(f"Downloading {file['url']} -> {local_path}")
            resp = await client.get(file["url"])
            resp.raise_for_status()
            async with aiofiles.open(local_path, "wb") as f:
                await f.write(resp.content)
            print(f"Saved: {local_path}")

    print("All files downloaded successfully.")


async def seed_initial_data() -> None:
    """Seed initial system data into the database safely (idempotent)."""

    await _fetch_media_files()

    with open(SEED_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    async with async_session_maker() as session:
        # ── Roles ─────────────────────────────────────────────────────────────
        roles = [
            {
                "id": deterministic_uuid("user_role", i["name"]),
                "name": i["name"],
                "description": i["description"],
            }
            for i in data.get("roles", [])
        ]
        await session.execute(
            insert(Role).values(roles).on_conflict_do_nothing(index_elements=["id"])
        )

        # ── Reaction Types ────────────────────────────────────────────────────
        reactions = [
            {
                "id": deterministic_uuid("reaction_type", i["name"]),
                "name": i["name"],
                "path": i["path"],
            }
            for i in data.get("reaction_types", [])
        ]
        await session.execute(
            insert(ReactionType)
            .values(reactions)
            .on_conflict_do_nothing(index_elements=["id"])
        )

        # ── Categories ────────────────────────────────────────────────────────
        categories = [
            {
                "id": deterministic_uuid("video_category", i["name"]),
                "name": i["name"],
            }
            for i in data.get("categories", [])
        ]
        await session.execute(
            insert(Category)
            .values(categories)
            .on_conflict_do_nothing(index_elements=["id"])
        )

        # ── Privacy Statuses ──────────────────────────────────────────────────
        privacy_statuses = [
            {
                "id": deterministic_uuid("privacy_status", i["name"]),
                "name": i["name"],
            }
            for i in data.get("privacy_statuses", [])
        ]
        await session.execute(
            insert(PrivacyStatus)
            .values(privacy_statuses)
            .on_conflict_do_nothing(index_elements=["id"])
        )

        # ── User Statuses ─────────────────────────────────────────────────────
        user_statuses = [
            {
                "id": deterministic_uuid("user_status", i["value"]),
                "value": i["value"],
            }
            for i in data.get("user_statuses", [])
        ]
        await session.execute(
            insert(UserStatus)
            .values(user_statuses)
            .on_conflict_do_nothing(index_elements=["id"])
        )

        # ── Video Statuses ────────────────────────────────────────────────────
        video_statuses = [
            {
                "id": deterministic_uuid("video_status", i["value"]),
                "value": i["value"],
            }
            for i in data.get("video_statuses", [])
        ]
        await session.execute(
            insert(VideoStatus)
            .values(video_statuses)
            .on_conflict_do_nothing(index_elements=["id"])
        )

        await session.commit()
        logging.info("Initial data seeded successfully.")

        # ── Users + Channels + Videos ─────────────────────────────────────────
        await seed_users_channels_videos(session)

        # ── One video through full pipeline (upload to S3 + broker) ──────────
        await seed_videos_via_service(session, USER_ID)
        logging.info("Videos seeded successfully.")


def main() -> None:
    asyncio.run(seed_initial_data())


if __name__ == "__main__":
    main()
