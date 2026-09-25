from src.core.base_error import AppError
from src.i18n import _


class NotificationNotFoundError(AppError):
    code = "NOTIFICATION_NOT_FOUND"
    status_code = 404

    def __init__(self) -> None:
        super().__init__(_("Notification not found"))
