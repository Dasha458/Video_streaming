"""
Integration tests run against a real PostgreSQL started by Testcontainers.

Why not mocks: the unit suite (tests/*.py) overrides get_async_session with
an AsyncMock, which is right for router wiring but proves nothing about the
SQL itself -- the window/delta queries in AnalyticsService and the joined
pagination in LikedService are exactly where a mocked session would pass
while the real query is wrong.

Isolation: one container per test session, schema created from the ORM
models, and every test runs inside a transaction that is rolled back at
the end. Services may call session.commit() freely -- the session is bound
to an outer connection transaction with join_transaction_mode=
"create_savepoint", so their commits only release a savepoint.

If Docker isn't reachable the whole directory is skipped, so the unit
suite stays runnable on a machine without Docker.
"""

import uuid
from collections.abc import AsyncGenerator, Generator
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine

# NOTE: no `src.*` imports at module level anywhere in this file. src/__init__.py
# eagerly imports the whole app (api -> infrastructure.database -> config ->
# get_vault_client()), which raises unless tests/conftest.py's pytest_configure
# has already patched src.core.vault into sys.modules -- and conftest.py
# files are imported before any pytest_configure hook runs. Every src.* symbol
# below is imported lazily, inside the function/fixture that needs it, exactly
# like tests/conftest.py's own docstring requires for test modules.

# The engine/session fixtures are session-scoped (one container, one pool for
# the whole run), so every test's own asyncio event loop must be session-scoped
# too -- otherwise asyncpg connections opened on the session loop get used
# from a test's own function-scoped loop and asyncpg raises "Future attached
# to a different loop". Per-test @pytest.mark.asyncio(loop_scope="session")
# does NOT reliably achieve this under asyncio_mode="auto"; run pytest with
# `-o asyncio_default_test_loop_scope=session -o asyncio_default_fixture_loop_scope=session`
# (already set in ci/python.yml's test-integration-python job).
pytestmark = pytest.mark.integration


def _start_postgres():
    try:
        # Moved package in testcontainers 4.x; the old path still works but
        # warns. Fall back so an older pin keeps running.
        try:
            from testcontainers.community.postgres import PostgresContainer
        except ImportError:  # pragma: no cover - testcontainers < 4.13
            from testcontainers.postgres import PostgresContainer
    except ImportError:  # pragma: no cover - dev dep missing
        pytest.skip("testcontainers is not installed")
    try:
        container = PostgresContainer("postgres:16-alpine", driver="asyncpg")
        container.start()
    except Exception as exc:  # docker unavailable / not running
        pytest.skip(f"Docker is not available for integration tests: {exc}")
    return container


@pytest.fixture(scope="session")
def postgres_url() -> Generator[str, None, None]:
    container = _start_postgres()
    yield container.get_connection_url()
    container.stop()


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def engine(postgres_url: str) -> AsyncGenerator[AsyncEngine, None]:
    # Importing the models package registers every table on Base.metadata.
    import src.models  # noqa: F401
    from src.infrastructure.database import Base

    engine = create_async_engine(postgres_url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(_seed_lookups)
    yield engine
    await engine.dispose()


REACTION_LIKE_ID = uuid.uuid5(uuid.NAMESPACE_DNS, "reaction_type:like")
REACTION_DISLIKE_ID = uuid.uuid5(uuid.NAMESPACE_DNS, "reaction_type:dislike")
CATEGORY_ID = uuid.uuid5(uuid.NAMESPACE_DNS, "video_category:general")


def _seed_lookups(sync_conn) -> None:
    """The rows the app assumes exist: statuses, privacy levels, reactions,
    one category. Ids match src/core/status_ids.py so the services' hardcoded
    lookups resolve."""
    from sqlalchemy import insert

    from src.core.status_ids import (
        PRIVACY_PRIVATE_ID,
        PRIVACY_PUBLIC_ID,
        STATUS_FAILED_ID,
        STATUS_PROCESSING_ID,
        STATUS_QUEUED_ID,
        STATUS_READY_ID,
    )
    from src.models import Category, PrivacyStatus, ReactionType, VideoStatus

    sync_conn.execute(
        insert(VideoStatus),
        [
            {"id": STATUS_READY_ID, "value": "ready"},
            {"id": STATUS_PROCESSING_ID, "value": "processing"},
            {"id": STATUS_QUEUED_ID, "value": "queued"},
            {"id": STATUS_FAILED_ID, "value": "failed"},
        ],
    )
    sync_conn.execute(
        insert(PrivacyStatus),
        [
            {"id": PRIVACY_PUBLIC_ID, "name": "public"},
            {"id": PRIVACY_PRIVATE_ID, "name": "private"},
        ],
    )
    sync_conn.execute(
        insert(ReactionType),
        [
            {"id": REACTION_LIKE_ID, "name": "like"},
            {"id": REACTION_DISLIKE_ID, "name": "dislike"},
        ],
    )
    sync_conn.execute(insert(Category), [{"id": CATEGORY_ID, "name": "general"}])


@pytest_asyncio.fixture(loop_scope="session")
async def session(engine: AsyncEngine) -> AsyncGenerator[AsyncSession, None]:
    """A session whose every write is rolled back after the test."""
    async with engine.connect() as conn:
        await conn.begin()
        async_session = AsyncSession(
            bind=conn,
            expire_on_commit=False,
            join_transaction_mode="create_savepoint",
        )
        try:
            yield async_session
        finally:
            await async_session.close()
            await conn.rollback()


# ── Data builders ────────────────────────────────────────────────────────────
# Plain helpers, not fixtures: tests compose exactly the graph they need.


def now() -> datetime:
    return datetime.now(UTC)


def days_ago(n: int) -> datetime:
    return now() - timedelta(days=n)


async def make_user(session: AsyncSession, *, username: str | None = None):
    from src.models import User

    uid = uuid.uuid4()
    user = User(
        id=uid,
        email=f"{uid.hex[:8]}@example.com",
        username=username or f"user_{uid.hex[:8]}",
        hashed_password="x",
        is_active=True,
        is_superuser=False,
        is_verified=True,
    )
    session.add(user)
    await session.flush()
    return user


async def make_channel(session: AsyncSession, owner, *, name: str | None = None):
    from src.models import Channel

    channel = Channel(
        id=uuid.uuid4(),
        name=name or f"chan_{uuid.uuid4().hex[:8]}",
        user_id=owner.id,
        subscribers_count=0,
        views_count=0,
    )
    session.add(channel)
    await session.flush()
    return channel


async def make_video(
    session: AsyncSession,
    channel,
    *,
    name: str = "video",
    privacy_id: uuid.UUID | None = None,
    status_id: uuid.UUID | None = None,
    created_at: datetime | None = None,
):
    from src.core.status_ids import PRIVACY_PUBLIC_ID, STATUS_READY_ID
    from src.models import Video

    privacy_id = privacy_id or PRIVACY_PUBLIC_ID
    status_id = status_id or STATUS_READY_ID

    video = Video(
        id=uuid.uuid4(),
        name=name,
        description=None,
        size=1,
        hash=uuid.uuid4().hex,
        channel_id=channel.id,
        privacy_id=privacy_id,
        category_id=CATEGORY_ID,
        status_id=status_id,
        created_at=created_at or now(),
    )
    session.add(video)
    await session.flush()
    return video


async def add_view(
    session: AsyncSession, video, *, at: datetime, user=None, source: str | None = None
):
    from src.models import VideoView

    session.add(
        VideoView(
            id=uuid.uuid4(),
            video_id=video.id,
            user_id=user.id if user else None,
            viewed_at=at,
            source_type=source,
        )
    )
    await session.flush()


async def add_reaction(
    session: AsyncSession,
    video,
    user,
    *,
    reaction_id=REACTION_LIKE_ID,
    at: datetime | None = None,
):
    from src.models import VideoReaction

    session.add(
        VideoReaction(
            id=uuid.uuid4(),
            video_id=video.id,
            user_id=user.id,
            reaction_type_id=reaction_id,
            created_at=at or now(),
        )
    )
    # src.services.reactions.toggle_reaction keeps Video.likes_count/
    # dislikes_count in sync with the reaction rows on every real write;
    # mirror that here since this helper inserts rows directly.
    if reaction_id == REACTION_LIKE_ID:
        video.likes_count += 1
    elif reaction_id == REACTION_DISLIKE_ID:
        video.dislikes_count += 1
    await session.flush()


async def add_watch_session(
    session: AsyncSession,
    video,
    *,
    watched: int,
    duration: int = 100,
    at: datetime | None = None,
    user=None,
):
    from src.models import VideoWatchSession

    session.add(
        VideoWatchSession(
            id=uuid.uuid4(),
            video_id=video.id,
            user_id=user.id if user else None,
            started_at=at or now(),
            watched_seconds=watched,
            video_duration_seconds=duration,
            completed_percent=watched / duration if duration else 0.0,
        )
    )
    await session.flush()
