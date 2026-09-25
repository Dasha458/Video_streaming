"""
Convertor test configuration.

The convertor's src/config.py calls hvac.Client() at module level.
We must mock hvac before any src.* module is imported.
"""

import sys
import types
from unittest.mock import MagicMock

import pytest


def pytest_configure(config: pytest.Config) -> None:
    """Mock hvac before src.config is imported."""
    # Build a fake hvac module
    mock_hvac = types.ModuleType("hvac")
    mock_hvac.exceptions = types.ModuleType("hvac.exceptions")  # type: ignore[attr-defined]
    sys.modules["hvac"] = mock_hvac
    sys.modules["hvac.exceptions"] = mock_hvac.exceptions  # type: ignore[attr-defined]

    # hvac.Client(url=..., token=...) → mock client where is_authenticated() = True
    mock_client = MagicMock()
    mock_client.is_authenticated.return_value = True

    _secrets: dict = {
        "s3": {
            "MINIO_ROOT_USER": "minioadmin",
            "MINIO_ROOT_PASSWORD": "minioadmin",
            "MINIO_ENDPOINT_URL": "http://localhost:9000",
            "MINIO_REGION_NAME": "us-east-1",
            "BUCKET_NAMES": "videos,video-thumbnails",
        },
        "rabbitmq": {
            "RABBITMQ_HOST": "localhost",
            "RABBITMQ_PORT": "5672",
            "RABBITMQ_USER": "guest",
            "RABBITMQ_PASSWORD": "guest",
        },
    }

    def _read_secret(path: str, mount_point: str = "secret") -> dict:
        return _secrets.get(path, {})

    mock_client.secrets = MagicMock()
    mock_client.secrets.kv = MagicMock()
    mock_client.secrets.kv.v2 = MagicMock()
    mock_client.secrets.kv.v2.read_secret_version = MagicMock(
        side_effect=lambda path, mount_point="secret": {
            "data": {"data": _secrets.get(path, {})}
        }
    )

    mock_hvac.Client = MagicMock(return_value=mock_client)  # type: ignore[attr-defined]
