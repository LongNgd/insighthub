"""ARQ worker that executes the existing atomic ingestion pipeline."""

import asyncio
import json
import logging
from datetime import UTC, datetime
from typing import Any

from arq import Retry
from arq.connections import RedisSettings

from app.core.config import get_settings
from app.core.db import close_pool, initialize_database
from app.core.errors import DocumentNotFound, ProviderError, ServiceError
from app.services.ingestion import process_document

logger = logging.getLogger("insighthub.ingestion_worker")


def _log(event: str, document_id: int, status: str, attempt: int, error_code: str | None = None) -> None:
    record: dict[str, Any] = {
        "event": event,
        "document_id": document_id,
        "status": status,
        "attempt": attempt,
        "timestamp": datetime.now(UTC).isoformat(),
    }
    if error_code is not None:
        record["error_code"] = error_code
    logger.info(json.dumps(record, ensure_ascii=False))


async def startup(_: dict[str, Any]) -> None:
    await asyncio.to_thread(initialize_database)


async def shutdown(_: dict[str, Any]) -> None:
    await asyncio.to_thread(close_pool)


async def process_document_job(
    ctx: dict[str, Any], document_id: int, filename: str, content: bytes
) -> int:
    """Process once; transient provider errors receive at most three attempts."""
    attempt = int(ctx.get("job_try", 1))
    final_attempt = attempt >= get_settings().worker_max_retries
    try:
        chunk_count = await asyncio.to_thread(
            process_document,
            document_id,
            filename,
            content,
            retryable_failure=not final_attempt,
        )
    except DocumentNotFound:
        _log("ingestion_deleted", document_id, "deleted", attempt)
        return 0
    except ProviderError as exc:
        if not final_attempt:
            _log("ingestion_retry_scheduled", document_id, "pending", attempt, exc.code)
            raise Retry(defer=2 ** (attempt - 1)) from None
        _log("ingestion_failed", document_id, "failed", attempt, exc.code)
        raise
    except ServiceError as exc:
        _log("ingestion_failed", document_id, "failed", attempt, exc.code)
        raise
    _log("ingestion_completed", document_id, "ready", attempt)
    return chunk_count


class WorkerSettings:
    functions = [process_document_job]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
    max_tries = get_settings().worker_max_retries
