from src.core.base_error import AppError
from src.i18n import _


class UploadNotFoundError(AppError):
    """No such upload, or not this user's.

    Ownership is enforced as part of the lookup, so the two cases are
    deliberately one error: answering differently would confirm that
    somebody else's upload id exists.
    """

    code = "UPLOAD_NOT_FOUND"
    status_code = 404

    def __init__(self) -> None:
        super().__init__(_("Upload not found"))


class PartTooSmallError(AppError):
    """A part below the minimum, which would make the assembled file
    unreadable.

    Storage only reports this at completion, by which point every other
    part has been sent for nothing. Refusing the part as it arrives costs
    one request instead of the whole upload.
    """

    code = "UPLOAD_PART_INVALID"
    status_code = 400

    def __init__(self, detail: str) -> None:
        super().__init__(detail)


class UploadSizeMismatchError(AppError):
    """The assembled file is not the size the client said it would be.

    The declared size decides whether the upload is allowed to start, so
    it has to be checked again against what actually arrived -- otherwise
    declaring one megabyte and sending two gigabytes would work.
    """

    code = "UPLOAD_SIZE_MISMATCH"
    status_code = 400

    def __init__(self, detail: str) -> None:
        super().__init__(detail)
