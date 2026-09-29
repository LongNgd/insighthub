"""
InsightHub ChatOps Bot — sanitized audit log.

Mọi tool call của bot PHẢI được ghi audit. Đây là yêu cầu bảo mật cốt lõi:
khi AI agent có quyền chạm vào hạ tầng, phải có dấu vết kiểm toán.

"""
import json
import logging
import os
from collections.abc import Mapping
from datetime import datetime, timezone
from uuid import uuid4

logger = logging.getLogger("chatops-bot.audit")


def log_tool_call(
    user: str,
    tool: str,
    args: Mapping[str, object],
    result_summary: str,
    approved: bool = True,
) -> None:
    """
    Ghi 1 dòng audit cho mỗi tool call.

    Emit one structured JSON record without argument values or result content.
    A future log sink may forward these already-sanitized records to an
    aggregator. Callers must not use this function for raw Slack payloads.
    """
    log_audit_event(
        event_id=str(uuid4()),
        user=user,
        action=tool,
        decision="allowed" if approved else "denied",
        summary="present" if result_summary else "empty",
        argument_keys=_safe_argument_keys(args),
    )


def log_audit_event(
    *,
    event_id: str,
    user: str,
    action: str,
    decision: str,
    summary: str,
    argument_keys: list[str] | None = None,
) -> None:
    """Emit the mandatory correlation fields without raw event or tool content."""

    run_id = os.getenv("INSIGHTHUB_VERIFY_RUN_ID", "")
    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "event_id": event_id,
        "run_id": run_id,
        "test_run_id": run_id,
        "user": user,
        "action": action,
        "decision": decision,
        "argument_keys": argument_keys or [],
        "result_summary": summary,
    }
    logger.info(json.dumps(record, ensure_ascii=False, sort_keys=True))


def _safe_argument_keys(args: Mapping[str, object]) -> list[str]:
    """Retain audit shape while dropping values that could contain private data."""

    sensitive_markers = ("secret", "token", "signature", "password", "body", "payload")
    safe_keys: list[str] = []
    for key in sorted(str(item) for item in args):
        if any(marker in key.lower() for marker in sensitive_markers):
            safe_keys.append("[redacted]")
        else:
            safe_keys.append(key)
    return safe_keys
