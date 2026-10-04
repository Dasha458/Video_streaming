"""
Centralized deterministic UUIDs for video status / privacy lookup values.

These act as foreign keys into the video_statuses / privacy_statuses tables
and are computed once via ``uuid5(NAMESPACE_DNS, "<domain>:<name>")``.
Previously this call was duplicated with hand-typed strings across 6+ files
(services/videos.py, services/files.py, schemas/video.py, models/video.py,
services/analytics.py, infrastructure/messaging/rabbit_subscriptions.py) --
a typo in any one of them silently produced a UUID matching nothing in the
DB, with no compile-time or DB-level protection. This module is now the
single source of truth; every other file imports from here.
"""

from uuid import NAMESPACE_DNS, UUID, uuid5

# ── Video status ────────────────────────────────────────────────────────────

STATUS_READY_ID: UUID = uuid5(NAMESPACE_DNS, "video_status:ready")
STATUS_PROCESSING_ID: UUID = uuid5(NAMESPACE_DNS, "video_status:processing")
STATUS_QUEUED_ID: UUID = uuid5(NAMESPACE_DNS, "video_status:queued")
STATUS_FAILED_ID: UUID = uuid5(NAMESPACE_DNS, "video_status:failed")

STATUS_LABELS: dict[UUID, str] = {
    STATUS_READY_ID: "Ready",
    STATUS_PROCESSING_ID: "Processing",
    STATUS_QUEUED_ID: "Queued",
    STATUS_FAILED_ID: "Failed",
}

STATUS_ID_BY_NAME: dict[str, UUID] = {
    "ready": STATUS_READY_ID,
    "processing": STATUS_PROCESSING_ID,
    "queued": STATUS_QUEUED_ID,
    "failed": STATUS_FAILED_ID,
}


def status_id_for(name: str) -> UUID | None:
    """Look up the status UUID for a known status name (case-insensitive).

    Returns ``None`` for an unrecognized name instead of silently deriving
    a UUID that matches nothing in the DB.
    """
    return STATUS_ID_BY_NAME.get(name.lower())


# ── Privacy ─────────────────────────────────────────────────────────────────

PRIVACY_PUBLIC_ID: UUID = uuid5(NAMESPACE_DNS, "privacy_status:public")
PRIVACY_PRIVATE_ID: UUID = uuid5(NAMESPACE_DNS, "privacy_status:private")

PRIVACY_LABELS: dict[UUID, str] = {
    PRIVACY_PUBLIC_ID: "public",
    PRIVACY_PRIVATE_ID: "private",
}

PRIVACY_ID_BY_NAME: dict[str, UUID] = {
    "public": PRIVACY_PUBLIC_ID,
    "private": PRIVACY_PRIVATE_ID,
}


def privacy_id_for(name: str) -> UUID | None:
    """Look up the privacy UUID for a known privacy name (case-insensitive)."""
    return PRIVACY_ID_BY_NAME.get(name.lower())


# ── Category ────────────────────────────────────────────────────────────────


def category_id_for(name: str) -> UUID:
    """The id of a category, derived the same way the seed data was.

    The last of the hand-written ``uuid5`` calls: this one was still
    spelled out in services/files.py and services/videos.py, so the two
    could have drifted apart in exactly the way this module exists to
    prevent. The input is constrained by a Literal on the request
    schema, which is why it never bit -- not a reason to leave it.

    Unlike statuses and privacy there is no fixed list here: categories
    are rows, and new ones can be added without touching this file. A
    name no row matches produces an id no row matches, which the foreign
    key then refuses -- the same answer, from the database rather than
    from a guess here.
    """
    return uuid5(NAMESPACE_DNS, f"video_category:{name.lower()}")
