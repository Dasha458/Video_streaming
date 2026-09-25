from src.core.base_error import AppError
from src.i18n import _


class PlaylistNotFoundError(AppError):
    code = "PLAYLIST_NOT_FOUND"
    status_code = 404

    def __init__(self) -> None:
        super().__init__(_("Playlist not found"))


class PlaylistAccessForbiddenError(AppError):
    code = "PLAYLIST_ACCESS_FORBIDDEN"
    status_code = 403

    def __init__(self) -> None:
        super().__init__(_("You do not own this playlist"))


class VideoAlreadyInPlaylistError(AppError):
    code = "VIDEO_ALREADY_IN_PLAYLIST"
    status_code = 409

    def __init__(self) -> None:
        super().__init__(_("Video is already in this playlist"))


class VideoNotInPlaylistError(AppError):
    code = "VIDEO_NOT_IN_PLAYLIST"
    status_code = 404

    def __init__(self) -> None:
        super().__init__(_("Video is not in this playlist"))
