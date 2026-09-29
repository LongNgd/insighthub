"""Default-deny, structured audit records for ChatOps execution boundaries."""

import json
import logging
import os
import re
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Final

from app.config import Settings, get_settings
from app.errors import AuditUnavailable


logger = logging.getLogger("chatops-bot.audit")

_DECISIONS: Final = frozenset({"allowed", "denied", "approval_required"})
_ACTIONS: Final = frozenset(
    {
        "event_enqueue",
        "event_process",
        "approved_action_process",
        "insighthub_health",
        "insighthub_documents_today",
        "kubernetes_failed_pods",
        "scale_deployment",
        "policy",
    }
)
_TOOLS: Final = frozenset(
    {
        "queue",
        "worker",
        "policy",
        "mcp.insighthub_health",
        "mcp.prometheus_summary",
        "mcp.insighthub_ingest_count_today_utc",
        "mcp.kubernetes.get_pods",
        "kubernetes.patch_deployment_scale",
    }
)
_SUMMARIES: Final = frozenset(
    {
        "queued",
        "duplicate",
        "queue_unavailable",
        "audit_unavailable",
        "invalid_event",
        "reply_sent",
        "reply_already_sent",
        "retry_scheduled",
        "retry_exhausted",
        "permanent_processing_error",
        "transient_processing_error",
        "unclassified_failure",
        "mcp_success",
        "mcp_unavailable",
        "mcp_schema_error",
        "write_approval_required",
        "approval_missing",
        "approval_identity_denied",
        "approval_invalid",
        "approval_recorded",
        "action_denied",
        "confirmation_required",
        "confirmation_invalid",
        "confirmation_issued",
        "execution_dispatched",
        "execution_completed",
        "executor_failed",
        "reconciliation_required",
        "request_missing",
        "sanitized",
    }
)
_APPROVAL_STATES: Final = frozenset(
    {
        "not_required",
        "approval_required",
        "approved",
        "consumed",
        "denied",
        "unavailable",
    }
)
_SLACK_USER_ID = re.compile(r"^[A-Z][A-Z0-9]{1,63}$")


def ensure_audit_sink_available(settings: Settings | None = None) -> None:
    """Fail before a protected tool call when its configured audit sink is unavailable."""

    current = settings or get_settings()
    if current.audit_sink == "stdout":
        return
    try:
        with Path(current.audit_file).open("a", encoding="utf-8"):
            pass
    except OSError as error:
        raise AuditUnavailable() from error


def log_tool_call(
    user: str,
    tool: str,
    args: Mapping[str, object],
    result_summary: str,
    approved: bool = True,
) -> None:
    """Compatibility wrapper that deliberately discards arbitrary arguments/results."""

    _ = args, result_summary
    log_audit_event(
        event_id="unknown",
        run_id="unknown",
        user=user,
        action="policy",
        tool=tool,
        decision="allowed" if approved else "denied",
        approval_state="not_required",
        summary="sanitized",
    )


def log_audit_event(
    *,
    event_id: str,
    run_id: str,
    user: str,
    action: str,
    tool: str,
    decision: str,
    summary: str,
    approval_state: str,
    approver_user_id: str | None = None,
) -> None:
    """Emit exactly one safe JSON record for an execution or policy boundary."""

    record = {
        "timestamp": _utc_timestamp(),
        "event_id": _opaque_identifier(event_id),
        "run_id": _opaque_identifier(run_id),
        "user": _safe_user(user),
        "action": action if action in _ACTIONS else "unknown",
        "tool": tool if tool in _TOOLS else "unknown",
        "decision": decision if decision in _DECISIONS else "denied",
        "approval": _approval(approval_state, approver_user_id),
        "summary": summary if summary in _SUMMARIES else "sanitized",
        "test_run_id": _test_run_id(),
    }
    serialized = json.dumps(record, ensure_ascii=True, separators=(",", ":"), sort_keys=True)
    current = get_settings()
    ensure_audit_sink_available(current)
    try:
        if current.audit_sink == "stdout":
            logger.info(serialized)
        else:
            with Path(current.audit_file).open("a", encoding="utf-8") as sink:
                sink.write(serialized + "\n")
                sink.flush()
        _write_verification_observation(record)
    except (OSError, TypeError, ValueError) as error:
        raise AuditUnavailable() from error


def _utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _opaque_identifier(value: str) -> str:
    if isinstance(value, str) and 1 <= len(value) <= 128 and value.isascii():
        return value
    return "unknown"


def _safe_user(value: str) -> str:
    return value if isinstance(value, str) and _SLACK_USER_ID.fullmatch(value) else "unknown"


def _approval(state: str, approver_user_id: str | None) -> dict[str, str]:
    value = state if state in _APPROVAL_STATES else "unavailable"
    record = {"state": value}
    if approver_user_id is not None and _safe_user(approver_user_id) != "unknown":
        record["approver_user_id"] = approver_user_id
    return record


def _test_run_id() -> str | None:
    value = os.getenv("INSIGHTHUB_VERIFY_RUN_ID", "")
    return _opaque_identifier(value) if value else None


def _write_verification_observation(record: dict[str, object]) -> None:
    """Append sanitized test observations only when the verifier explicitly requests it."""

    output_path = os.getenv("INSIGHTHUB_VERIFY_OBSERVATIONS", "")
    test_run_id = _test_run_id()
    if not output_path or test_run_id is None:
        return
    path = Path(output_path)
    try:
        existing = json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
        if existing is None:
            envelope: dict[str, object] = {"run_id": test_run_id, "events": []}
        elif (
            isinstance(existing, dict)
            and existing.get("run_id") == test_run_id
            and isinstance(existing.get("events"), list)
        ):
            envelope = existing
        else:
            raise ValueError("invalid verification observation envelope")
        events = envelope["events"]
        if not isinstance(events, list):
            raise ValueError("invalid verification observation events")
        events.append(record)
        path.write_text(
            json.dumps(envelope, ensure_ascii=True, separators=(",", ":"), sort_keys=True),
            encoding="utf-8",
        )
    except (OSError, TypeError, ValueError) as error:
        raise AuditUnavailable() from error
