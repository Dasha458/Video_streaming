from src.core.base_error import AppError
from src.i18n import _


class HistoryEntryNotFoundError(AppError):
    code = "HISTORY_ENTRY_NOT_FOUND"
    status_code = 404

    def __init__(self) -> None:
        super().__init__(_("History entry not found"))
