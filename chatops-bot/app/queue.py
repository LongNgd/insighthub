"""Redis/ARQ queue adapter for authenticated Slack events only."""

from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from arq import ArqRedis, create_pool
from arq.connections import RedisSettings

from app.audit import log_audit_event
from app.config import get_settings
from app.errors import QueueUnavailable
from app.events import NormalizedSlackEvent


PROCESS_EVENT_JOB = "process_slack_event_job"

_pool: ArqRedis | None = None


@dataclass(frozen=True)
class EnqueueResult:
    """Whether the authenticated event was newly queued or already claimed."""

    accepted: bool


async def initialize_queue() -> ArqRedis:
    """Create the lazy shared Redis connection used by the HTTP transport."""

    global _pool
    if _pool is None:
        settings = get_settings()
        if not settings.redis_url:
            raise QueueUnavailable()
        try:
            _pool = await create_pool(RedisSettings.from_dsn(settings.redis_url))
        except Exception as error:
            raise QueueUnavailable() from error
    return _pool


async def close_queue() -> None:
    """Close the queue connection during application shutdown or tests."""

    global _pool
    if _pool is not None:
        await _pool.aclose()
        _pool = None


async def enqueue_authenticated_event(event: NormalizedSlackEvent) -> EnqueueResult:
    """Atomically claim a Slack identity, then durably submit exactly one ARQ job."""

    settings = get_settings()
    try:
        pool = await initialize_queue()
    except QueueUnavailable:
        _log_enqueue_failure(event)
        raise
    dedup_key = _dedup_key(event)
    claim_token = str(uuid4())
    try:
        claimed = await pool.set(
            dedup_key,
            f"claimed:{claim_token}",
            nx=True,
            ex=settings.dedup_ttl_seconds,
        )
    except Exception as error:
        _log_enqueue_failure(event)
        raise QueueUnavailable() from error
    if not claimed:
        log_audit_event(
            event_id=event.identity,
            user=event.user_id,
            action="event_enqueue",
            decision="denied",
            summary="duplicate",
        )
        return EnqueueResult(accepted=False)

    try:
        job: Any = await pool.enqueue_job(
            PROCESS_EVENT_JOB,
            event.to_job_payload(),
            _queue_name=settings.queue_name,
        )
    except Exception as error:
        await _release_claim(pool, dedup_key, claim_token)
        _log_enqueue_failure(event)
        raise QueueUnavailable() from error
    if job is None:
        await _release_claim(pool, dedup_key, claim_token)
        _log_enqueue_failure(event)
        raise QueueUnavailable()

    try:
        await pool.set(
            dedup_key,
            f"queued:{claim_token}",
            xx=True,
            ex=settings.dedup_ttl_seconds,
        )
    except Exception:
        # enqueue_job already acknowledged durable persistence. The original claim
        # remains, so a Slack redelivery still cannot create a second job.
        pass
    log_audit_event(
        event_id=event.identity,
        user=event.user_id,
        action="event_enqueue",
        decision="allowed",
        summary="queued",
    )
    return EnqueueResult(accepted=True)


def _dedup_key(event: NormalizedSlackEvent) -> str:
    return f"chatops:dedup:{event.identity}"


def _log_enqueue_failure(event: NormalizedSlackEvent) -> None:
    """Record a queue failure without provider details or the Slack payload."""

    log_audit_event(
        event_id=event.identity,
        user=event.user_id,
        action="event_enqueue",
        decision="denied",
        summary="queue_unavailable",
    )


async def _release_claim(pool: ArqRedis, key: str, claim_token: str) -> None:
    """Delete only this request's failed claim; never release another request."""

    release_script = (
        "if redis.call('GET', KEYS[1]) == ARGV[1] then "
        "return redis.call('DEL', KEYS[1]) else return 0 end"
    )
    try:
        await pool.eval(release_script, 1, key, f"claimed:{claim_token}")
    except Exception:
        # Let the short-lived claim expire rather than opening a duplicate race.
        pass
