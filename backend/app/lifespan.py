import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Awaitable, cast

from fastapi import FastAPI
from prometheus_client import Info

from src.infrastructure.database import engine
from src.infrastructure.elasticsearch import es_client
from src.infrastructure.messaging.client import get_rabbit_broker
from src.infrastructure.redis.client import get_redis
from src.infrastructure.s3_client import get_s3_client
from src.schemas.search import VideoIndexMapping
from src.services.metrics import APP_NAME

APP_INFO = Info("fastapi_app", "FastAPI Application Information")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator:
    # Prometheus metrics
    APP_INFO.info({"app_name": APP_NAME})

    # Start RabbitMQ
    rabbit_broker = await get_rabbit_broker()
    await rabbit_broker.start()
    logging.info("Rabbit broker connected successfully.")

    # Check S3
    s3_client = get_s3_client()
    await s3_client.check_bucket_exists()
    logging.info("S3 connected successfully and bucket exists.")

    # Ensure the Elasticsearch index exists
    exists = await es_client.indices.exists(index=VideoIndexMapping.index_name)
    if not exists:
        await es_client.indices.create(
            index=VideoIndexMapping.index_name,
            mappings=VideoIndexMapping.mappings,
            settings=VideoIndexMapping.settings,
        )
    logging.info("ElasticSearch index verified/created.")
    logging.info("Startup complete. Metrics exposed.")

    redis = get_redis()
    # redis-py types commands as `Awaitable[T] | T`; on the async client it is
    # always the awaitable branch.
    await cast(Awaitable[bool], redis.ping())
    print("Redis connected successfully.")

    logging.info("🚀 Startup complete. Background tasks running.")
    yield

    # Graceful shutdown
    await es_client.close()
    logging.info("Elasticsearch client closed gracefully.")
    await rabbit_broker.stop()
    logging.info("Rabbit broker connection disposed gracefully.")
    await engine.dispose()
    logging.info("Database engine disposed gracefully.")

    await redis.aclose()
    print("Redis connection closed.")
    logging.info("Background tasks cancelled.")
    logging.info("Shutdown complete.")
