from src.core.base_error import AppError
from src.i18n import _


class ChannelAlreadyExistsError(AppError):
    code = "CHANNEL_ALREADY_EXISTS"
    status_code = 409

    def __init__(self) -> None:
        super().__init__(_("You already have a channel"))


class ChannelNameTakenError(AppError):
    code = "CHANNEL_NAME_TAKEN"
    status_code = 409

    def __init__(self) -> None:
        super().__init__(_("Channel name is already taken"))


class ChannelNotFoundError(AppError):
    code = "CHANNEL_NOT_FOUND"
    status_code = 404

    def __init__(self) -> None:
        super().__init__(_("Channel not found"))


class AlreadySubscribedError(AppError):
    code = "ALREADY_SUBSCRIBED"
    status_code = 409

    def __init__(self) -> None:
        super().__init__(_("You are already subscribed to this channel"))


class NotSubscribedError(AppError):
    code = "NOT_SUBSCRIBED"
    status_code = 409

    def __init__(self) -> None:
        super().__init__(_("You are not subscribed to this channel"))


class CannotSubscribeOwnChannelError(AppError):
    code = "CANNOT_SUBSCRIBE_OWN_CHANNEL"
    status_code = 400

    def __init__(self) -> None:
        super().__init__(_("You cannot subscribe to your own channel"))
