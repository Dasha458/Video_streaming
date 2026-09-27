"""
The notifications this application can raise.

Each event used to be assembled by hand at the call site -- the message
text, the link and the type string written out inline in three different
services, with no one place to see what the app notifies about or to
check that a type string was spelled the same way twice. They are builders
rather than writers: they return the row, and the caller adds it to the
session that is already open, so the notification commits in the same
transaction as the thing that caused it.

``NotificationService.create_notification`` committed on its own, which
is why it was never used by any of these call sites.
"""

from uuid import UUID

from src.models import Notification

NEW_SUBSCRIBER = "new_subscriber"
NEW_COMMENT = "new_comment"
COMMENT_REPLY = "comment_reply"


def new_subscriber(*, channel_owner_id: UUID, channel_name: str) -> Notification:
    return Notification(
        user_id=channel_owner_id,
        content="Someone subscribed to your channel",
        link=f"/channel/{channel_name}",
        notification_type=NEW_SUBSCRIBER,
    )


def new_comment(*, channel_owner_id: UUID, video_id: UUID) -> Notification:
    return Notification(
        user_id=channel_owner_id,
        content="Someone commented on your video",
        link=f"/watch?v={video_id}",
        notification_type=NEW_COMMENT,
    )


def comment_reply(*, parent_author_id: UUID, video_id: UUID) -> Notification:
    return Notification(
        user_id=parent_author_id,
        content="Someone replied to your comment",
        link=f"/watch?v={video_id}",
        notification_type=COMMENT_REPLY,
    )
