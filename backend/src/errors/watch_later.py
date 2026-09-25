from src.core.base_error import AppError
from src.i18n import _


class AlreadyInWatchLaterError(AppError):
    code = "ALREADY_IN_WATCH_LATER"
    status_code = 409

    def __init__(self) -> None:
        super().__init__(_("Video is already in watch later"))


class WatchLaterEntryNotFoundError(AppError):
    code = "WATCH_LATER_ENTRY_NOT_FOUND"
    status_code = 404

    def __init__(self) -> None:
        super().__init__(_("Watch later entry not found"))
