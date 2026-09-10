"""ARQ job policy for the shared ingestion pipeline."""

import asyncio
import datetime as dt
import json
import logging
from typing import Any

from arq import Retry
from arq.connections import RedisSettings

from app.core.config import get_settings
from app.core.db import close_pool, initialize_database
from app.core.errors import (
    DocumentConflict,
    DocumentNotFound,
    IndexIdentityConflict,
    InvalidDocument,
    ProviderError,
    SchemaMismatch,
    ServiceError,
)
from app.services.ingestion import process_document

logger = logging.getLogger("insighthub.ingestion_worker")
logger.propagate = False
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(handler)
logger.setLevel(logging.INFO)

PERMANENT_ERRORS = (
    InvalidDocument,
    DocumentConflict,
    DocumentNotFound,
    IndexIdentityConflict,
    SchemaMismatch,
)
MAX_ATTEMPTS = 3


def _log_event(event: str, document_id: int, status: str, **fields: Any) -> None:
    payload = {
        "event": event,
        "document_id": document_id,
        "status": status,
        "timestamp": dt.datetime.now(dt.timezone.utc).isoformat(),
        **fields,
    }
    logger.info(json.dumps(payload, separators=(",", ":")))


async def ingest_document(
    ctx: dict[str, Any], document_id: int, filename: str, content: bytes
) -> int:
    attempt = int(ctx.get("job_try", 1))
    try:
        chunk_count = await asyncio.to_thread(
            process_document, document_id, filename, content
        )
    except PERMANENT_ERRORS as exc:
        _log_event("ingestion_failed", document_id, "failed", error_code=exc.code)
        raise
    except (ProviderError, ServiceError) as exc:
        if attempt < MAX_ATTEMPTS:
            _log_event(
                "ingestion_retrying",
                document_id,
                "failed",
                error_code=exc.code,
                attempt=attempt,
            )
            raise Retry(defer=2 ** (attempt - 1)) from None
        _log_event(
            "ingestion_failed",
            document_id,
            "failed",
            error_code=exc.code,
            attempt=attempt,
        )
        raise
    _log_event("ingestion_completed", document_id, "ready", chunk_count=chunk_count)
    return chunk_count


async def startup(ctx: dict[str, Any]) -> None:
    # The ARQ CLI configures logging after module import; suppress argument reprs here.
    logging.getLogger("arq.worker").setLevel(logging.WARNING)
    await asyncio.to_thread(initialize_database)


async def shutdown(ctx: dict[str, Any]) -> None:
    await asyncio.to_thread(close_pool)


class WorkerSettings:
    functions = [ingest_document]
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
    on_startup = startup
    on_shutdown = shutdown
    max_tries = MAX_ATTEMPTS
    job_timeout = int(get_settings().provider_timeout_seconds) + 120
    keep_result = 0
