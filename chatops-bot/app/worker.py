"""ARQ worker for durable, bounded ChatOps event processing."""

from typing import Any

from arq import Retry
from arq.connections import RedisSettings
from redis.exceptions import RedisError

from app.audit import log_audit_event
from app.config import get_settings
from app.errors import (
    ChatopsError,
    EventValidationError,
    PermanentProcessingError,
    TransientProcessingError,
)
from app.events import NormalizedSlackEvent
from app.intents import route_authenticated_event
from app.intents import IntentResult
from app.policy import create_scale_request, execute_approved_request
from app.action_executor import KubernetesScaleExecutor
from app.slack_reply import send_deferred_reply


async def process_slack_event_job(ctx: dict[str, Any], payload: dict[str, Any]) -> None:
    """Run an allowlisted intent and reply once, retrying transient failures only."""

    try:
        event = NormalizedSlackEvent.from_job_payload(payload)
    except EventValidationError:
        log_audit_event(
            event_id="invalid_event",
            user="unknown",
            action="event_process",
            decision="denied",
            summary="invalid_event",
        )
        raise
    attempt = int(ctx.get("job_try", 1))
    settings = get_settings()
    try:
        request = await create_scale_request(ctx["redis"], event)
        if request is None:
            result = await route_authenticated_event(event)
        else:
            result = IntentResult(
                action=request.action,
                reply_text=(
                    "Scale request received. An allowlisted, distinct approver must "
                    f"approve request {request.request_id} before any action is taken."
                ),
                approval_request_id=request.request_id,
            )
        reply_state = await _claim_reply(
            ctx["redis"], event, str(ctx.get("job_id", event.identity))
        )
        if reply_state == "sent":
            log_audit_event(
                event_id=event.identity,
                user=event.user_id,
                action=result.action,
                decision="allowed",
                summary="reply_already_sent",
            )
            return
        if reply_state == "in_progress":
            raise TransientProcessingError()
        if result.approval_request_id is None:
            await send_deferred_reply(event, result.reply_text)
        else:
            await send_deferred_reply(
                event,
                result.reply_text,
                approval_request_id=result.approval_request_id,
            )
        try:
            await ctx["redis"].set(
                _reply_key(event), "sent", xx=True, ex=settings.reply_ttl_seconds
            )
        except RedisError as error:
            raise TransientProcessingError() from error
    except TransientProcessingError as error:
        if attempt < settings.worker_max_tries:
            log_audit_event(
                event_id=event.identity,
                user=event.user_id,
                action="event_process",
                decision="allowed",
                summary="retry_scheduled",
            )
            raise Retry(defer=_retry_delay(attempt)) from None
        log_audit_event(
            event_id=event.identity,
            user=event.user_id,
            action="event_process",
            decision="denied",
            summary="retry_exhausted",
        )
        raise error from None
    except (EventValidationError, PermanentProcessingError) as error:
        log_audit_event(
            event_id=event.identity,
            user=event.user_id,
            action="event_process",
            decision="denied",
            summary=error.code,
        )
        raise error from None
    except RedisError as error:
        if attempt < settings.worker_max_tries:
            log_audit_event(
                event_id=event.identity,
                user=event.user_id,
                action="event_process",
                decision="allowed",
                summary="retry_scheduled",
            )
            raise Retry(defer=_retry_delay(attempt)) from None
        log_audit_event(
            event_id=event.identity,
            user=event.user_id,
            action="event_process",
            decision="denied",
            summary="retry_exhausted",
        )
        raise TransientProcessingError() from error
    except Exception as error:
        # Unknown errors are never silently retried: they have not been classified
        # as a transient provider failure and could otherwise loop forever.
        log_audit_event(
            event_id=event.identity,
            user=event.user_id,
            action="event_process",
            decision="denied",
            summary="unclassified_failure",
        )
        raise error
    log_audit_event(
        event_id=event.identity,
        user=event.user_id,
        action=result.action,
        decision="allowed",
        summary="reply_sent",
    )


async def process_approved_action_job(ctx: dict[str, Any], request_id: str) -> None:
    """Execute one approved mutation without ARQ retrying its side effect."""

    try:
        await execute_approved_request(
            ctx["redis"], request_id, KubernetesScaleExecutor()
        )
    except Exception as error:
        # Policy/executor functions already emit sanitized decision audit records.
        # Returning prevents ARQ's generic retry mechanism from repeating a write.
        log_audit_event(
            event_id=request_id,
            user="unknown",
            action="approved_action_process",
            decision="denied",
            summary=error.code if isinstance(error, ChatopsError) else "unclassified_failure",
        )
        return


async def _claim_reply(redis: Any, event: NormalizedSlackEvent, job_id: str) -> str:
    """Atomically reserve one reply sender while preserving a stable retry owner."""

    claim_script = (
        "local value = redis.call('GET', KEYS[1]); "
        "if value == 'sent' then return 'sent' end; "
        "if not value then redis.call('SET', KEYS[1], ARGV[1], 'EX', ARGV[2]); "
        "return 'claimed' end; "
        "if value == ARGV[1] then return 'claimed' end; return 'in_progress'"
    )
    settings = get_settings()
    try:
        value = await redis.eval(
            claim_script,
            1,
            _reply_key(event),
            f"sending:{job_id}",
            settings.reply_ttl_seconds,
        )
    except RedisError as error:
        raise TransientProcessingError() from error
    if isinstance(value, bytes):
        value = value.decode("utf-8", errors="replace")
    if value not in {"sent", "claimed", "in_progress"}:
        raise TransientProcessingError()
    return value


def _reply_key(event: NormalizedSlackEvent) -> str:
    return f"chatops:reply:{event.identity}"


def _retry_delay(attempt: int) -> float:
    settings = get_settings()
    return min(
        settings.retry_base_seconds * (2 ** (attempt - 1)),
        settings.retry_max_seconds,
    )


class WorkerSettings:
    """ARQ CLI entrypoint; missing Redis configuration fails closed at startup."""

    functions = [process_slack_event_job, process_approved_action_job]
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
    queue_name = get_settings().queue_name
    max_tries = get_settings().worker_max_tries
