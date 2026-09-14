from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from src.api.dependencies.services import get_channel_service
from src.schemas.channel import ChannelCreate, ChannelResponse, ChannelSubscriptionItem, ChannelUpdate
from src.schemas.endpoint import ErrorResponse
from src.services.dependencies import get_current_user_id, get_optional_user_id
from src.services.channels import ChannelService

router_channels = APIRouter(
    prefix="/api/channels",
    tags=["channels"],
    default_response_class=JSONResponse,
    responses={
        404: {"description": "Not found"},
        500: {"description": "Internal server error"},
    },
)


@router_channels.post(
    "",
    response_model=ChannelResponse,
    status_code=201,
    summary="Create channel",
    description="Creates a channel for the authenticated user.",
    responses={
        409: {"model": ErrorResponse, "description": "User already has a channel or name is taken."},
    },
)
async def create_channel(
    data: ChannelCreate,
    user_id: UUID = Depends(get_current_user_id),
    service: ChannelService = Depends(get_channel_service),
) -> ChannelResponse:
    return await service.create_channel(user_id, data)


@router_channels.get(
    "/me",
    response_model=ChannelResponse | None,
    summary="Get my channel",
    description="Returns the authenticated user's channel, or null if they don't have one.",
)
async def get_my_channel(
    user_id: UUID = Depends(get_current_user_id),
    service: ChannelService = Depends(get_channel_service),
) -> ChannelResponse | None:
    return await service.get_my_channel(user_id)


@router_channels.patch(
    "/me",
    response_model=ChannelResponse,
    summary="Update my channel",
    description="Updates the authenticated user's channel name or description.",
    responses={
        404: {"model": ErrorResponse, "description": "User has no channel."},
        409: {"model": ErrorResponse, "description": "Channel name is already taken."},
    },
)
async def update_my_channel(
    data: ChannelUpdate,
    user_id: UUID = Depends(get_current_user_id),
    service: ChannelService = Depends(get_channel_service),
) -> ChannelResponse:
    return await service.update_channel(user_id, data)


@router_channels.get(
    "/subscriptions",
    response_model=List[ChannelSubscriptionItem],
    summary="Get my subscriptions",
    description="Returns all channels the authenticated user is subscribed to.",
)
async def get_subscriptions(
    user_id: UUID = Depends(get_current_user_id),
    service: ChannelService = Depends(get_channel_service),
) -> List[ChannelSubscriptionItem]:
    return await service.get_subscriptions(user_id)


@router_channels.get(
    "/{channel_name}",
    response_model=ChannelResponse,
    summary="Get channel by name",
    description="Returns public information about a channel.",
    responses={
        404: {"model": ErrorResponse, "description": "Channel not found."},
    },
)
async def get_channel(
    channel_name: str,
    user_id: UUID | None = Depends(get_optional_user_id),
    service: ChannelService = Depends(get_channel_service),
) -> ChannelResponse:
    return await service.get_by_name(channel_name, user_id)


@router_channels.post(
    "/{channel_name}/subscribe",
    status_code=204,
    summary="Subscribe to a channel",
    responses={
        409: {"model": ErrorResponse, "description": "Already subscribed or own channel."},
        404: {"model": ErrorResponse, "description": "Channel not found."},
    },
)
async def subscribe(
    channel_name: str,
    user_id: UUID = Depends(get_current_user_id),
    service: ChannelService = Depends(get_channel_service),
) -> None:
    await service.subscribe(channel_name, user_id)


@router_channels.post(
    "/{channel_name}/unsubscribe",
    status_code=204,
    summary="Unsubscribe from a channel",
    responses={
        409: {"model": ErrorResponse, "description": "Not subscribed."},
        404: {"model": ErrorResponse, "description": "Channel not found."},
    },
)
async def unsubscribe(
    channel_name: str,
    user_id: UUID = Depends(get_current_user_id),
    service: ChannelService = Depends(get_channel_service),
) -> None:
    await service.unsubscribe(channel_name, user_id)
