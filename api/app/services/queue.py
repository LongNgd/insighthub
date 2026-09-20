"""Durable ARQ queue adapter used by the HTTP request path."""

from typing import Any

from arq import ArqRedis, create_pool
from arq.connections import RedisSettings

from app.core.config import get_settings
from app.core.errors import QueueUnavailable

_pool: ArqRedis | None = None


async def initialize_queue() -> None:
    """Create the shared Redis client when it is needed by a request."""
    global _pool
    if _pool is None:
        try:
            _pool = await create_pool(
                RedisSettings.from_dsn(get_settings().redis_url)
            )
        except Exception as exc:
            raise QueueUnavailable() from exc


async def close_queue() -> None:
    """Close the shared Redis client during API shutdown."""
    global _pool
    if _pool is not None:
        await _pool.aclose()
        _pool = None


async def enqueue_document(document_id: int, filename: str, content: bytes) -> None:
    """Enqueue an ingestion request without exposing queue implementation details."""
    await initialize_queue()
    assert _pool is not None
    try:
        job: Any = await _pool.enqueue_job(
            "process_document_job", document_id, filename, content
        )
    except Exception as exc:
        raise QueueUnavailable() from exc
    if job is None:
        raise QueueUnavailable()
