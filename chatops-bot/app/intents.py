"""Server-side allowlist for read-only ChatOps intents."""

import asyncio
from dataclasses import dataclass
from collections.abc import Mapping
from typing import Awaitable, Callable, TypeVar

from app.audit import ensure_audit_sink_available, log_audit_event
from app.errors import McpSchemaError, McpUnavailable, PermanentProcessingError, TransientProcessingError
from app.events import NormalizedSlackEvent
from app.mcp_client import (
    ERRORS_5M,
    REQUESTS_5M,
    get_readonly_mcp_client,
    validate_health,
    validate_ingest_count,
    validate_metric,
)


@dataclass(frozen=True)
class IntentResult:
    """A sanitized reply produced by an allowlisted read-only intent."""

    action: str
    reply_text: str
    approval_request_id: str | None = None


IntentHandler = Callable[[NormalizedSlackEvent], Awaitable[IntentResult]]
Validated = TypeVar("Validated")


async def route_authenticated_event(event: NormalizedSlackEvent) -> IntentResult:
    """Route only the three explicit Day 5 read-only intent names."""

    if event.event_type != "app_mention":
        raise PermanentProcessingError()
    intent = _intent_name(event.text)
    handler = _ALLOWED_INTENTS.get(intent)
    if handler is None:
        raise PermanentProcessingError()
    try:
        return await asyncio.wait_for(handler(event), timeout=get_settings_timeout())
    except TimeoutError as error:
        raise TransientProcessingError() from error


def _intent_name(text: str) -> str:
    """Map fixed command forms; text never becomes a tool name or arguments."""

    normalized = " ".join(text.casefold().split())
    if normalized in {"health", "insighthub health"}:
        return "insighthub_health"
    if normalized in {"documents today", "ingest today"}:
        return "insighthub_documents_today"
    if normalized in {"failed pods", "pods failed"}:
        return "kubernetes_failed_pods"
    return ""


async def _health(event: NormalizedSlackEvent) -> IntentResult:
    client = get_readonly_mcp_client()
    live, ready, database_ready = await _call(
        event,
        "insighthub_health",
        "mcp.insighthub_health",
        client.health(),
        validate_health,
    )
    requests, errors = await asyncio.gather(
        _prometheus_context(event, client.prometheus_requests_5m(), REQUESTS_5M),
        _prometheus_context(event, client.prometheus_errors_5m(), ERRORS_5M),
    )
    status = "healthy" if live and ready and database_ready else "degraded"
    context = (
        "Prometheus context unavailable; check the read-only metrics backend."
        if requests is None or errors is None
        else f"Prometheus 5m: requests={_format_metric(requests)}, errors={_format_metric(errors)}."
    )
    return IntentResult(
        "insighthub_health",
        f"InsightHub is {status}: live={live}, ready={ready}, database_ready={database_ready}. {context}",
    )


async def _documents_today(event: NormalizedSlackEvent) -> IntentResult:
    date, count = await _call(
        event,
        "insighthub_documents_today",
        "mcp.insighthub_ingest_count_today_utc",
        get_readonly_mcp_client().ingest_count_today_utc(),
        validate_ingest_count,
    )
    return IntentResult(
        "insighthub_documents_today",
        f"Documents ingested on {date} (UTC): {count}. Recommendation: use this aggregate for triage; document metadata is not exposed.",
    )


async def _failed_pods(event: NormalizedSlackEvent) -> IntentResult:
    from app.config import get_settings
    from app.mcp_client import summarize_abnormal_pods

    settings = get_settings()
    try:
        pods = await _call(
            event,
            "kubernetes_failed_pods",
            "mcp.kubernetes.get_pods",
            get_readonly_mcp_client().pods(),
            lambda result: summarize_abnormal_pods(
                result,
                restart_threshold=settings.kubernetes_restart_threshold,
                maximum=settings.kubernetes_max_pods,
            ),
        )
    except (McpUnavailable, McpSchemaError):
        return IntentResult(
            "kubernetes_failed_pods",
            f"Pod triage is unavailable for configured namespace {settings.kubernetes_namespace}. Recommendation: check the read-only Kubernetes MCP connection and RBAC.",
        )
    if not pods:
        return IntentResult(
            "kubernetes_failed_pods",
            f"No abnormal pods found in configured namespace {settings.kubernetes_namespace}. Recommendation: continue monitoring; no action was taken.",
        )
    details = "; ".join(pods)
    return IntentResult(
        "kubernetes_failed_pods",
        f"Pod triage for configured namespace {settings.kubernetes_namespace}: {details}. Recommendation: inspect the reported workload through approved read-only diagnostics; no action was taken.",
    )


async def _call(
    event: NormalizedSlackEvent,
    action: str,
    tool: str,
    operation: Awaitable[Mapping[str, object]],
    validator: Callable[[Mapping[str, object]], Validated],
) -> Validated:
    """Audit one fixed capability call without retaining inputs or provider output."""

    ensure_audit_sink_available()
    try:
        result = validator(await operation)
    except McpUnavailable:
        log_audit_event(
            event_id=event.identity,
            run_id=event.run_id,
            user=event.user_id,
            action=action,
            tool=tool,
            decision="denied",
            approval_state="not_required",
            summary="mcp_unavailable",
        )
        raise
    except McpSchemaError:
        log_audit_event(
            event_id=event.identity,
            run_id=event.run_id,
            user=event.user_id,
            action=action,
            tool=tool,
            decision="denied",
            approval_state="not_required",
            summary="mcp_schema_error",
        )
        raise
    log_audit_event(
        event_id=event.identity,
        run_id=event.run_id,
        user=event.user_id,
        action=action,
        tool=tool,
        decision="allowed",
        approval_state="not_required",
        summary="mcp_success",
    )
    return result


async def _prometheus_context(
    event: NormalizedSlackEvent,
    operation: Awaitable[Mapping[str, object]],
    query: str,
) -> float | None:
    try:
        return await _call(
            event,
            "insighthub_health",
            "mcp.prometheus_summary",
            operation,
            lambda result: validate_metric(result, query),
        )
    except (McpUnavailable, McpSchemaError):
        return None


def _format_metric(value: float | None) -> str:
    return "unavailable" if value is None else f"{value:g}"


_ALLOWED_INTENTS: dict[str, IntentHandler] = {
    "insighthub_health": _health,
    "insighthub_documents_today": _documents_today,
    "kubernetes_failed_pods": _failed_pods,
}


def get_settings_timeout() -> float:
    """Read the bounded router timeout without creating a prompt-controlled path."""

    from app.config import get_settings

    return get_settings().intent_timeout_seconds
