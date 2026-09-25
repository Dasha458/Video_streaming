from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.config import get_github_oauth_settings
from src.i18n import InternationalizationMiddleware
from src.services.metrics import PrometheusMiddleware


def _cors_origins() -> list[str]:
    """CORS origins, derived from the single configurable FRONTEND_URL
    setting instead of a hardcoded list. Both the localhost and 127.0.0.1
    forms are allowed for whichever one FRONTEND_URL points at, since
    browsers treat them as different origins during local development.
    """
    frontend_url = get_github_oauth_settings().FRONTEND_URL
    origins = {frontend_url}
    if "localhost" in frontend_url:
        origins.add(frontend_url.replace("localhost", "127.0.0.1"))
    elif "127.0.0.1" in frontend_url:
        origins.add(frontend_url.replace("127.0.0.1", "localhost"))
    return list(origins)


def add_middlewares(app: FastAPI) -> None:
    origins = _cors_origins()

    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH"],
        allow_headers=["*"],
    )
    app.add_middleware(InternationalizationMiddleware)
    app.add_middleware(PrometheusMiddleware)
