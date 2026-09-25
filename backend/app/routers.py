from fastapi import FastAPI

from src.api.analytics import router_analytics
from src.api.auth import router_auth
from src.api.changelog import router_changelog
from src.api.channels import router_channels
from src.api.comments import router_comments
from src.api.files import router_files
from src.api.health import router_health
from src.api.history import router_history
from src.api.liked import router_liked
from src.api.metrics import router_metrics
from src.api.notifications import router_notifications
from src.api.playlists import router_playlists
from src.api.search import router_search
from src.api.videos import router_videos
from src.api.watch_later import router_watch_later
from src.infrastructure.messaging.rabbit_subscriptions import rabbit_router


def include_routers(app: FastAPI) -> None:
    app.include_router(router_health)
    app.include_router(router_files)
    app.include_router(router_metrics)
    app.include_router(router_videos)
    app.include_router(router_comments)
    app.include_router(rabbit_router)
    app.include_router(router_search)
    app.include_router(router_auth)
    app.include_router(router_analytics)
    app.include_router(router_channels)
    app.include_router(router_history)
    app.include_router(router_watch_later)
    app.include_router(router_playlists)
    app.include_router(router_notifications)
    app.include_router(router_liked)
    app.include_router(router_changelog)
