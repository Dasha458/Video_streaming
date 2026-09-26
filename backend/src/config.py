from functools import lru_cache
from typing import List

from pydantic import Field, computed_field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from src.core.vault import VaultClient


@lru_cache()
def get_vault_client() -> VaultClient:
    return VaultClient()


class BaseAppSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file_encoding="utf-8")


# Every field below is required: the application cannot run without it, and
# declaring them Optional only meant a missing Vault key surfaced later as a
# confusing connection error (and left every use of them unchecked by mypy).
# Required means pydantic names the missing key at startup instead.
class DatabaseSettings(BaseAppSettings):
    POSTGRES_HOST: str
    POSTGRES_PORT: str
    POSTGRES_DB: str
    POSTGRES_USER: str
    POSTGRES_PASSWORD: str

    @computed_field  # type: ignore[prop-decorator]
    @property
    def database_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )


class S3Settings(BaseAppSettings):
    MINIO_ROOT_USER: str
    MINIO_ROOT_PASSWORD: str
    MINIO_ENDPOINT_URL: str
    MINIO_REGION_NAME: str
    BUCKET_NAMES: List[str]


class ElasticSettings(BaseAppSettings):
    ELASTIC_HOST: str
    ELASTIC_PASSWORD: str


class JWTSettings(BaseAppSettings):
    JWT_SECRET: str = Field(default="CHANGE-ME-IN-PRODUCTION")

    @field_validator("JWT_SECRET")
    @classmethod
    def jwt_secret_must_be_strong(cls, v: str) -> str:
        if v == "CHANGE-ME-IN-PRODUCTION" or len(v) < 32:
            raise ValueError(
                "JWT_SECRET must be set to a strong random value of at least 32 characters. "
                'Generate one with: python -c "import secrets; print(secrets.token_hex(32))"'
            )
        return v


class GitHubOAuthSettings(BaseAppSettings):
    GITHUB_CLIENT_ID: str = Field(default="")
    GITHUB_CLIENT_SECRET: str = Field(default="")
    GITHUB_CALLBACK_URL: str = Field(
        default="http://localhost:8000/api/auth/github/callback"
    )
    FRONTEND_URL: str = Field(default="http://localhost:5173")


class RedisSettings(BaseAppSettings):
    REDIS_HOST: str
    REDIS_PORT: int


class RABBITMQSettings(BaseAppSettings):
    RABBITMQ_HOST: str
    RABBITMQ_PORT: str
    RABBITMQ_USER: str
    RABBITMQ_PASSWORD: str

    @computed_field  # type: ignore[prop-decorator]
    @property
    def rabbitmq_url(self) -> str:
        return (
            f"amqp://{self.RABBITMQ_USER}:{self.RABBITMQ_PASSWORD}"
            f"@{self.RABBITMQ_HOST}:{self.RABBITMQ_PORT}/"
        )


@lru_cache()
def get_database_settings() -> DatabaseSettings:
    vault = get_vault_client()
    return DatabaseSettings(**vault.read_secret("database", mount_point="secret"))


@lru_cache()
def get_s3_settings() -> S3Settings:
    vault = get_vault_client()
    data = vault.read_secret("s3", mount_point="secret")
    data["BUCKET_NAMES"] = [b.strip() for b in data["BUCKET_NAMES"].split(",")]
    return S3Settings(**data)


@lru_cache()
def get_elastic_settings() -> ElasticSettings:
    vault = get_vault_client()
    return ElasticSettings(**vault.read_secret("elastic", mount_point="secret"))


@lru_cache()
def get_jwt_settings() -> JWTSettings:
    vault = get_vault_client()
    return JWTSettings(**vault.read_secret("jwt", mount_point="secret"))


@lru_cache()
def get_github_oauth_settings() -> GitHubOAuthSettings:
    vault = get_vault_client()
    return GitHubOAuthSettings(
        **vault.read_secret("github_oauth", mount_point="secret")
    )


@lru_cache()
def get_redis_settings() -> RedisSettings:
    vault = get_vault_client()
    return RedisSettings(**vault.read_secret("redis", mount_point="secret"))


@lru_cache()
def get_rabbitmq_settings() -> RABBITMQSettings:
    vault = get_vault_client()
    return RABBITMQSettings(**vault.read_secret("rabbitmq", mount_point="secret"))
