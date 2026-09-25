"""
Session-wide test configuration.

CRITICAL: The pytest_configure hook runs before any test modules are imported,
which is required because database.py, messaging/client.py, elasticsearch.py,
and infrastructure/auth.py all execute Vault-dependent code at module level.
"""

import sys
import types
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient

# ─────────────────────────────────────────────────────────────────────────────
# Test constants
# ─────────────────────────────────────────────────────────────────────────────
TEST_USER_ID = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
TEST_USER_EMAIL = "testuser@example.com"
TEST_USER_USERNAME = "testuser"

# ─────────────────────────────────────────────────────────────────────────────
# 1. Vault mock — MUST run before any src.* module is imported
# ─────────────────────────────────────────────────────────────────────────────

_SECRETS_BY_PATH: dict = {
    "database": {
        "POSTGRES_USER": "postgres",
        "POSTGRES_PASSWORD": "postgres",
        "POSTGRES_HOST": "localhost",
        "POSTGRES_PORT": "5432",
        "POSTGRES_DB": "video_streaming",
    },
    "s3": {
        "MINIO_ROOT_USER": "minioadmin",
        "MINIO_ROOT_PASSWORD": "minioadmin",
        "MINIO_ENDPOINT_URL": "http://localhost:9000",
        "MINIO_REGION_NAME": "us-east-1",
        "BUCKET_NAMES": "videos,video-thumbnails",
    },
    "elastic": {
        "ELASTIC_HOST": "http://localhost:9200",
        "ELASTIC_PASSWORD": "changeme",
    },
    "jwt": {
        "JWT_SECRET": "test-secret-key-min-32-chars-long!!",
    },
    "github_oauth": {
        "GITHUB_CLIENT_ID": "test-client-id",
        "GITHUB_CLIENT_SECRET": "test-client-secret",
        "GITHUB_CALLBACK_URL": "http://localhost:8000/api/auth/github/callback",
        "FRONTEND_URL": "http://localhost:5173",
    },
    "redis": {
        "REDIS_HOST": "localhost",
        "REDIS_PORT": "6379",
    },
    "rabbitmq": {
        "RABBITMQ_HOST": "localhost",
        "RABBITMQ_PORT": "5672",
        "RABBITMQ_USER": "guest",
        "RABBITMQ_PASSWORD": "guest",
    },
}


def pytest_configure(config: pytest.Config) -> None:  # noqa: D401
    """Inject Vault mock before any src.* module is imported."""
    mock_module = types.ModuleType("src.infrastructure.vault")

    mock_client_instance = MagicMock()
    mock_client_instance.read_secret.side_effect = (
        lambda path, mount_point="secret": _SECRETS_BY_PATH.get(path, {})
    )

    mock_client_cls = MagicMock(return_value=mock_client_instance)
    mock_module.VaultClient = mock_client_cls  # type: ignore[attr-defined]
    sys.modules["src.infrastructure.vault"] = mock_module


# ─────────────────────────────────────────────────────────────────────────────
# 2. Clear lru_cache on every settings getter so each session starts fresh
# ─────────────────────────────────────────────────────────────────────────────
@pytest.fixture(scope="session", autouse=True)
def clear_settings_cache() -> None:
    from src.config import (
        get_database_settings,
        get_elastic_settings,
        get_github_oauth_settings,
        get_jwt_settings,
        get_rabbitmq_settings,
        get_redis_settings,
        get_s3_settings,
        get_vault_client,
    )

    for fn in (
        get_vault_client,
        get_database_settings,
        get_s3_settings,
        get_elastic_settings,
        get_jwt_settings,
        get_github_oauth_settings,
        get_redis_settings,
        get_rabbitmq_settings,
    ):
        fn.cache_clear()


# ─────────────────────────────────────────────────────────────────────────────
# 3. Infrastructure mocks
# ─────────────────────────────────────────────────────────────────────────────
@pytest.fixture(scope="session")
def mock_s3_client() -> AsyncMock:
    s3 = AsyncMock()
    s3.get_bucket_list = AsyncMock(return_value=["videos", "video-thumbnails"])
    s3.upload_file = AsyncMock(return_value=None)
    s3.upload_dir = AsyncMock(return_value=None)
    s3.delete_file = AsyncMock(return_value=None)
    s3.delete_prefix = AsyncMock(return_value=None)
    s3.generate_presigned_url = AsyncMock(
        return_value="http://localhost:9000/videos/test.mp4?sig=abc"
    )
    s3.download_file_stream = AsyncMock(return_value=iter([b"fake-chunk"]))
    return s3


@pytest.fixture(scope="session")
def mock_rabbit_broker() -> MagicMock:
    broker = MagicMock()
    broker.is_connected = True
    broker.publish = AsyncMock(return_value=None)
    broker.connect = AsyncMock(return_value=None)
    return broker


@pytest.fixture(scope="session")
def mock_es_client() -> AsyncMock:
    es = AsyncMock()
    es.search = AsyncMock(return_value={"hits": {"hits": [], "total": {"value": 0}}})
    es.index = AsyncMock(return_value={"result": "created"})
    es.delete = AsyncMock(return_value={"result": "deleted"})
    es.indices = AsyncMock()
    es.indices.exists = AsyncMock(return_value=True)
    es.indices.create = AsyncMock(return_value=None)
    # Elasticsearch suggest for autocomplete
    es_suggest_result = {
        "suggest": {
            "video-suggest": [
                {
                    "options": [
                        {"text": "test video", "_source": {"title": "test video"}}
                    ]
                }
            ]
        }
    }
    es.search = AsyncMock(return_value=es_suggest_result)
    return es


@pytest.fixture(scope="session")
def mock_redis() -> AsyncMock:
    redis = AsyncMock()
    redis.get = AsyncMock(return_value=None)
    redis.set = AsyncMock(return_value=True)
    redis.incr = AsyncMock(return_value=1)
    redis.expire = AsyncMock(return_value=True)
    redis.ping = AsyncMock(return_value=True)
    return redis


# ─────────────────────────────────────────────────────────────────────────────
# 4. Mock user and auth override
# ─────────────────────────────────────────────────────────────────────────────
@pytest.fixture(scope="session")
def mock_user() -> MagicMock:
    user = MagicMock()
    user.id = TEST_USER_ID
    user.email = TEST_USER_EMAIL
    user.username = TEST_USER_USERNAME
    user.is_active = True
    user.is_superuser = False
    user.is_verified = True
    user.created_at = datetime(2025, 1, 1, tzinfo=timezone.utc)
    user.hashed_password = "$2b$12$fakehash"
    # Make model_validate work
    user.__class__.__name__ = "User"
    return user


# ─────────────────────────────────────────────────────────────────────────────
# 5. App and client fixtures
# ─────────────────────────────────────────────────────────────────────────────
@pytest.fixture(scope="session")
def app(
    mock_s3_client: AsyncMock,
    mock_rabbit_broker: MagicMock,
    mock_es_client: AsyncMock,
    mock_redis: AsyncMock,
    mock_user: MagicMock,
):  # noqa: E501
    from main import create_app
    from src.infrastructure import (
        get_async_session,
        get_es_client,
        get_rabbit_broker,
        get_s3_client,
    )
    from src.infrastructure.auth import current_active_user, current_superuser
    from src.infrastructure.redis import get_redis

    _app = create_app(use_lifespan=False)

    # Each test gets a fresh session mock so per-test .execute side_effects work
    def _session_factory():
        session = AsyncMock()
        session.__aenter__ = AsyncMock(return_value=session)
        session.__aexit__ = AsyncMock(return_value=False)
        session.execute = AsyncMock(return_value=MagicMock())
        session.commit = AsyncMock(return_value=None)
        session.rollback = AsyncMock(return_value=None)
        session.close = AsyncMock(return_value=None)
        return session

    _app.dependency_overrides[get_async_session] = _session_factory
    _app.dependency_overrides[get_s3_client] = lambda: mock_s3_client
    _app.dependency_overrides[get_rabbit_broker] = lambda: mock_rabbit_broker
    _app.dependency_overrides[get_es_client] = lambda: mock_es_client
    _app.dependency_overrides[get_redis] = lambda: mock_redis

    # Default: authenticated as mock_user
    _app.dependency_overrides[current_active_user] = lambda: mock_user
    _app.dependency_overrides[current_superuser] = lambda: mock_user

    return _app


@pytest.fixture(scope="session")
def _shared_client(app) -> TestClient:
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def client(_shared_client: TestClient) -> TestClient:
    # One TestClient for the whole session (cheap), but a clean cookie jar per
    # test: login sets the httpOnly session cookie, and without this every
    # later "unauthenticated" test would silently send it.
    _shared_client.cookies.clear()
    return _shared_client


@pytest.fixture(scope="session")
def async_client(app) -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
