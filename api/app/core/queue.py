"""ARQ queue lifecycle and the narrow ingestion enqueue contract."""

import logging

from arq import create_pool
from arq.connections import ArqRedis, RedisSettings

from app.core.config import get_settings
from app.core.errors import QueueUnavailable

logger = logging.getLogger("insighthub.queue")
_redis: ArqRedis | None = None


async def initialize_queue() -> None:
    global _redis
    if _redis is None:
        _redis = await create_pool(RedisSettings.from_dsn(get_settings().redis_url))
        await _redis.ping()


async def close_queue() -> None:
    global _redis
    if _redis is not None:
        await _redis.aclose()
        _redis = None


async def enqueue_ingestion(document_id: int, filename: str, content: bytes) -> None:
    try:
        await initialize_queue()
        assert _redis is not None
        job = await _redis.enqueue_job(
            "ingest_document",
            document_id,
            filename,
            content,
            _job_id=f"ingestion:{document_id}",
        )
        if job is None:
            raise QueueUnavailable()
    except QueueUnavailable:
        raise
    except Exception:
        logger.warning(
            "Document enqueue failed: id=%s code=queue_unavailable", document_id
        )
        raise QueueUnavailable() from None
