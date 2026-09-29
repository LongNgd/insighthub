"""Server-side allowlist for read-only ChatOps intents."""

import asyncio
from dataclasses import dataclass
from typing import Awaitable, Callable

from app.errors import PermanentProcessingError, TransientProcessingError
from app.events import NormalizedSlackEvent


@dataclass(frozen=True)
class IntentResult:
    """A sanitized reply produced by an allowlisted read-only intent."""

    action: str
    reply_text: str


IntentHandler = Callable[[NormalizedSlackEvent], Awaitable[IntentResult]]


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
    _ = event
    return IntentResult("insighthub_health", "InsightHub health triage is queued.")


async def _documents_today(event: NormalizedSlackEvent) -> IntentResult:
    _ = event
    return IntentResult("insighthub_documents_today", "Today's document-ingest triage is queued.")


async def _failed_pods(event: NormalizedSlackEvent) -> IntentResult:
    _ = event
    return IntentResult("kubernetes_failed_pods", "Failed-pod triage is queued.")


_ALLOWED_INTENTS: dict[str, IntentHandler] = {
    "insighthub_health": _health,
    "insighthub_documents_today": _documents_today,
    "kubernetes_failed_pods": _failed_pods,
}


def get_settings_timeout() -> float:
    """Read the bounded router timeout without creating a prompt-controlled path."""

    from app.config import get_settings

    return get_settings().intent_timeout_seconds
