from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import List, Optional


class ChangelogEntry(BaseModel):
    date: str
    version: str
    improvements: Optional[List[str]] = None
    bugfixes: Optional[List[str]] = None
    newFeatures: Optional[List[str]] = None
    tags: Optional[List[str]] = None


CHANGELOG: List[ChangelogEntry] = [
    ChangelogEntry(
        date="2025-04-20",
        version="1.4.0",
        tags=["New Features", "Improvements"],
        newFeatures=[
            "Video analytics dashboard with views, watch time, retention charts",
            "Per-video analytics page with traffic sources breakdown",
            "Creator Studio with realtime viewer counter",
        ],
        improvements=[
            "Watch session heartbeat now tracks audience retention percentage",
            "Home page loads 20% faster with optimised HLS prefetch",
        ],
    ),
    ChangelogEntry(
        date="2025-03-15",
        version="1.3.0",
        tags=["New Features", "Bug Fixes"],
        newFeatures=[
            "Comment replies with nested display",
            "Save to playlist and Watch Later buttons on video player",
            "Playlist detail page with video management",
        ],
        bugfixes=[
            "Fixed video deletion returning 404 (wrong URL in API client)",
            "Fixed playlist cards linking to non-existent page",
        ],
    ),
    ChangelogEntry(
        date="2025-02-10",
        version="1.2.0",
        tags=["New Features"],
        newFeatures=[
            "GitHub OAuth login",
            "Channel creation flow for new users",
            "Channel subscribe / unsubscribe",
            "Notification system with unread badge",
        ],
        improvements=[
            "Profile page now supports editing username and bio",
            "Password change from profile settings",
        ],
    ),
    ChangelogEntry(
        date="2025-01-05",
        version="1.1.0",
        tags=["Improvements", "Bug Fixes"],
        improvements=[
            "HLS adaptive bitrate streaming (360p / 720p / 1080p)",
            "Thumbnail upload during video publish flow",
            "Category filter on home page",
        ],
        bugfixes=[
            "Fixed video stuck in Processing status after successful transcoding",
            "Fixed avatar not loading on channel page for new users",
        ],
    ),
    ChangelogEntry(
        date="2024-12-01",
        version="1.0.0",
        tags=["New Features"],
        newFeatures=[
            "Initial release — video upload, playback, and search",
            "User authentication with email + password",
            "Like / dislike reactions on videos and comments",
            "Watch history and liked videos pages",
        ],
    ),
]

router_changelog = APIRouter(
    prefix="/api/changelog",
    tags=["changelog"],
    default_response_class=JSONResponse,
)


@router_changelog.get(
    "",
    response_model=List[ChangelogEntry],
    summary="Get changelog",
    description="Returns the list of product changelog entries, newest first.",
)
async def get_changelog() -> List[ChangelogEntry]:
    return CHANGELOG
