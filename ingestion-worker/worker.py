"""ARQ worker that executes the existing atomic ingestion pipeline."""

import asyncio
import json
from datetime import UTC, datetime
from typing import Any

from arq import Retry
from arq.connections import RedisSettings
from arq.logs import default_log_config
from prometheus_client import Counter, Gauge, start_http_server

from app.core.config import get_settings
from app.core.db import close_pool, initialize_database
from app.core.errors import DocumentNotFound, ProviderError, ServiceError
from app.services.ingestion import process_document

# The ARQ CLI applies dictConfig after importing this module. Its INFO job
# representation includes uploaded bytes, so suppress ARQ INFO at the source.
SAFE_LOG_CONFIG = default_log_config(False)
SAFE_LOG_CONFIG["loggers"]["arq"]["level"] = "WARNING"

worker_ready = Gauge("insighthub_worker_ready", "ARQ worker startup completed")
worker_jobs_total = Counter(
    "insighthub_worker_jobs_total",
    "Ingestion job attempts by bounded outcome",
    ["outcome"],
)
for outcome in ("ready", "retry", "failed", "deleted"):
    worker_jobs_total.labels(outcome)

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
    print(json.dumps(record, ensure_ascii=False), flush=True)


async def startup(ctx: dict[str, Any]) -> None:
    await asyncio.to_thread(initialize_database)
    port = get_settings().worker_metrics_port
    if port:
        server, thread = start_http_server(port)
        ctx["metrics_server"] = (server, thread)
        worker_ready.set(1)


async def shutdown(ctx: dict[str, Any]) -> None:
    worker_ready.set(0)
    metrics_server = ctx.pop("metrics_server", None)
    if metrics_server is not None:
        server, thread = metrics_server
        server.shutdown()
        server.server_close()
        thread.join()
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
        worker_jobs_total.labels("deleted").inc()
        _log("ingestion_deleted", document_id, "deleted", attempt)
        return 0
    except ProviderError as exc:
        if not final_attempt:
            worker_jobs_total.labels("retry").inc()
            _log("ingestion_retry_scheduled", document_id, "pending", attempt, exc.code)
            raise Retry(defer=2 ** (attempt - 1)) from None
        worker_jobs_total.labels("failed").inc()
        _log("ingestion_failed", document_id, "failed", attempt, exc.code)
        raise
    except ServiceError as exc:
        worker_jobs_total.labels("failed").inc()
        _log("ingestion_failed", document_id, "failed", attempt, exc.code)
        raise
    worker_jobs_total.labels("ready").inc()
    _log("ingestion_completed", document_id, "ready", attempt)
    return chunk_count


class WorkerSettings:
    functions = [process_document_job]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
    max_tries = get_settings().worker_max_retries
