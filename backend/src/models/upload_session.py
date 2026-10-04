import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.infrastructure.database import Base

if TYPE_CHECKING:
    from .user import User


class UploadSession(Base):
    """One video being uploaded a piece at a time.

    A 500 MB file sent as a single request fails entirely on any dropped
    connection, and forces the gateway to accept a body that large from
    anyone. Uploading in parts costs one part on a drop, and no single
    request is ever bigger than a part.

    The row is the server's half of a resumable upload: which storage
    upload the parts belong to, who may add to it, and what the file was
    said to be. Which parts have actually arrived is not stored here --
    that is asked of storage, which is the thing that knows, and a row
    that disagreed with it would resume into a corrupt file.

    No video row exists until the upload completes. That is deliberate:
    the old single-shot path committed the video first and uploaded
    afterwards, so a storage failure left a row stuck in "queued" that
    its owner could not delete and whose hash blocked them re-uploading
    their own file.
    """

    __tablename__ = "upload_sessions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    #: Decided when the upload starts, so the parts are written straight
    #: to the key the video will use. Completing then needs no copy of a
    #: half-gigabyte object.
    video_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, unique=True
    )
    object_key: Mapped[str] = mapped_column(String(512), nullable=False)
    #: Storage's id for the multipart upload these parts belong to.
    storage_upload_id: Mapped[str] = mapped_column(String(512), nullable=False)
    filename: Mapped[str] = mapped_column(String(512), nullable=False)
    content_type: Mapped[str] = mapped_column(String(255), nullable=False)
    #: What the client said the file weighs. Checked again from the
    #: assembled object at completion, because this is a claim.
    declared_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    user: Mapped["User"] = relationship()

    __table_args__ = (
        Index("ix_upload_sessions_user_id", "user_id"),
        Index("ix_upload_sessions_created_at", "created_at"),
    )

    def __repr__(self) -> str:
        return f"<UploadSession {self.id} user={self.user_id} key={self.object_key}>"
