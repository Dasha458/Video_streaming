"""
Real-Postgres tests for the channel created on a first upload.

Channel.name is unique across the platform; usernames are their own
namespace. Nothing stops the two colliding, and the first upload by a
user whose name somebody else had already taken as a channel name hit an
IntegrityError and a 500 with nothing explaining why.

A savepoint per attempt matters here: an IntegrityError poisons the
transaction, so without one the first collision would take the whole
upload down with it.
"""

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.errors.files import ChannelNameUnavailableError
from src.models import Channel
from src.services.files import FileService
from tests.integration.conftest import make_channel, make_user

pytestmark = pytest.mark.integration


def _service(session: AsyncSession) -> FileService:
    return FileService(session=session, s3_client=AsyncMock(), broker=AsyncMock())


@pytest.mark.asyncio
async def test_a_first_upload_creates_the_channel(session: AsyncSession):
    user = await make_user(session, username="freshname")

    channel_id = await _service(session)._get_channel_id(user.id)

    name = await session.scalar(select(Channel.name).where(Channel.id == channel_id))
    assert name == "freshname"


@pytest.mark.asyncio
async def test_an_existing_channel_is_reused(session: AsyncSession):
    user = await make_user(session)
    existing = await make_channel(session, user)

    assert await _service(session)._get_channel_id(user.id) == existing.id


@pytest.mark.asyncio
async def test_a_name_somebody_else_took_does_not_break_the_upload(
    session: AsyncSession,
):
    """This was a 500 on the user's very first upload."""
    squatter = await make_user(session)
    await make_channel(session, squatter, name="popular")
    newcomer = await make_user(session, username="popular")

    channel_id = await _service(session)._get_channel_id(newcomer.id)

    name = await session.scalar(select(Channel.name).where(Channel.id == channel_id))
    assert name == "popular-2"


@pytest.mark.asyncio
async def test_it_keeps_trying_past_the_first_collision(session: AsyncSession):
    for taken in ("crowded", "crowded-2", "crowded-3"):
        await make_channel(session, await make_user(session), name=taken)
    newcomer = await make_user(session, username="crowded")

    channel_id = await _service(session)._get_channel_id(newcomer.id)

    name = await session.scalar(select(Channel.name).where(Channel.id == channel_id))
    assert name == "crowded-4"


@pytest.mark.asyncio
async def test_the_transaction_survives_the_collision(session: AsyncSession):
    """Without a savepoint the IntegrityError poisons the transaction and
    everything the caller is in the middle of goes with it."""
    await make_channel(session, await make_user(session), name="taken")
    newcomer = await make_user(session, username="taken")

    await _service(session)._get_channel_id(newcomer.id)

    # The session is still usable, which is the whole point.
    assert await session.scalar(select(Channel.id).limit(1)) is not None


@pytest.mark.asyncio
async def test_giving_up_says_so_rather_than_erroring(session: AsyncSession):
    """Twenty collisions is not a database failure, it is a person who
    needs to choose a name."""
    service = _service(session)
    service.CHANNEL_NAME_ATTEMPTS = 2
    await make_channel(session, await make_user(session), name="dense")
    await make_channel(session, await make_user(session), name="dense-2")
    newcomer = await make_user(session, username="dense")

    with pytest.raises(ChannelNameUnavailableError):
        await service._get_channel_id(newcomer.id)


@pytest.mark.asyncio
async def test_a_user_who_is_gone_has_no_channel_made_for_them(
    session: AsyncSession,
):
    from src.errors.files import ChannelNotFoundError

    with pytest.raises(ChannelNotFoundError):
        await _service(session)._get_channel_id(uuid4())
