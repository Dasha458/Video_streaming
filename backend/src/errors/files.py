from src.core.base_error import AppError
from src.i18n import _


class InvalidFilePathError(AppError):
    code = "INVALID_FILE_PATH"
    status_code = 400

    def __init__(self) -> None:
        super().__init__(_("Invalid file path format"))


class MediaAccessDeniedError(AppError):
    """One answer for every reason the gateway may not sign an object.

    403 rather than 404 because the gateway's auth subrequest only
    understands 401 and 403 as a refusal -- anything else it reports to
    the viewer as an internal error. Refusals are not distinguished from
    each other, so the status does not reveal whether the object exists.
    """

    code = "MEDIA_ACCESS_DENIED"
    status_code = 403

    def __init__(self) -> None:
        super().__init__(_("Not allowed to access this media"))


class FileNotFoundS3Error(AppError):
    code = "FILE_NOT_FOUND"
    status_code = 404

    def __init__(self) -> None:
        super().__init__(_("File not found in storage"))


class SignedUrlGenerationError(AppError):
    code = "SIGNED_URL_FAILED"
    status_code = 500

    def __init__(self) -> None:
        super().__init__(_("Failed to generate signed URL"))


class S3DeletionError(AppError):
    code = "S3_DELETION_FAILED"
    status_code = 500

    def __init__(self) -> None:
        super().__init__(_("Failed to delete files from storage"))


class ResolutionNotFoundError(AppError):
    code = "VIDEO_RESOLUTION_NOT_FOUND"
    status_code = 404

    def __init__(self, resolution: str) -> None:
        super().__init__(
            _("Video resolution '%(res)s' not found") % {"res": resolution}
        )


class S3DownloadError(AppError):
    code = "S3_DOWNLOAD_FAILED"
    status_code = 500

    def __init__(self, object_key: str) -> None:
        super().__init__(
            _("Failed to download file '%(key)s' from storage") % {"key": object_key}
        )


class InvalidVideoFormatError(AppError):
    code = "INVALID_VIDEO_FORMAT"
    status_code = 400

    def __init__(self) -> None:
        super().__init__(_("Invalid video format"))


class InvalidThumbnailFormatError(AppError):
    code = "INVALID_THUMBNAIL_FORMAT"
    status_code = 400

    def __init__(self) -> None:
        super().__init__(_("Invalid thumbnail format"))


class ChannelNameUnavailableError(AppError):
    """Every name derived from the username was already taken.

    Channel names are unique platform-wide while usernames are their own
    namespace, so the two can collide. This is the end of a long run of
    collisions rather than a single one -- at that point the person
    should choose a channel name rather than have one derived.
    """

    code = "CHANNEL_NAME_UNAVAILABLE"
    status_code = 409

    def __init__(self) -> None:
        super().__init__(
            _("Could not create a channel automatically; please choose a channel name")
        )


class ChannelNotFoundError(AppError):
    code = "CHANNEL_NOT_FOUND"
    status_code = 404

    def __init__(self) -> None:
        super().__init__(_("User does not have a channel"))


class VideoUploadFailedError(AppError):
    code = "VIDEO_UPLOAD_FAILED"
    status_code = 500

    def __init__(self) -> None:
        super().__init__(_("Failed to upload video to storage"))


class DuplicateVideoError(AppError):
    """The same file is already on the platform, uploaded by someone else.

    The platform stores a given file once; that is the rule, not an
    accident of the schema. The message says so in those words -- the old
    one talked about a hash, which told the uploader nothing about what
    to do, and it was the same message whether the earlier copy was
    theirs or a stranger's. Nothing about the other video is revealed.
    """

    code = "DUPLICATE_VIDEO"
    status_code = 409

    def __init__(self) -> None:
        super().__init__(
            _("This video is already on the platform and cannot be uploaded twice")
        )


class AlreadyUploadedError(AppError):
    """The uploader's own earlier copy -- which they can be told about."""

    code = "ALREADY_UPLOADED"
    status_code = 409

    def __init__(self) -> None:
        super().__init__(_("You have already uploaded this video"))


class JobPublishFailedError(AppError):
    code = "JOB_PUBLISH_FAILED"
    status_code = 500

    def __init__(self) -> None:
        super().__init__(_("Failed to publish encoding job"))


class FileTooLargeError(AppError):
    code = "FILE_TOO_LARGE"
    status_code = 400

    def __init__(self, file_size: int) -> None:
        super().__init__(
            _("The uploaded file exceeds " "the maximum allowed size of %(size)sMB")
            % {"size": file_size}
        )


class EmptyFileError(AppError):
    code = "EMPTY_FILE"
    status_code = 400

    def __init__(self) -> None:
        super().__init__(_("The uploaded file is empty"))


class DownloadNotReadyError(AppError):
    """Asked for before the encode finished."""

    code = "DOWNLOAD_NOT_READY"
    status_code = 409

    def __init__(self) -> None:
        super().__init__(
            _("This video is still being processed; the download is not ready yet")
        )


class DownloadUnavailableError(AppError):
    """Ready, but no downloadable file was ever built for it.

    True of everything uploaded before the converter started producing
    one, and of a video whose remux failed while the encode stood.
    """

    code = "DOWNLOAD_UNAVAILABLE"
    status_code = 404

    def __init__(self) -> None:
        super().__init__(_("No downloadable file is available for this video"))
