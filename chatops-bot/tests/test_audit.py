"""Security tests for the default-deny ChatOps audit sink and projection."""

import asyncio
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest

from app import intents
from app.audit import log_audit_event, log_tool_call
from app.config import get_settings
from app.errors import AuditUnavailable
from app.events import NormalizedSlackEvent


def run(coroutine: Any) -> Any:
    return asyncio.run(coroutine)


@pytest.fixture(autouse=True)
def configured_audit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CHATOPS_AUDIT_SINK", "stdout")
    monkeypatch.delenv("CHATOPS_AUDIT_FILE", raising=False)
    monkeypatch.delenv("INSIGHTHUB_VERIFY_RUN_ID", raising=False)
    monkeypatch.delenv("INSIGHTHUB_VERIFY_OBSERVATIONS", raising=False)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def event() -> NormalizedSlackEvent:
    return NormalizedSlackEvent(
        event_id="Ev-audit",
        run_id="00000000-0000-4000-8000-000000000007",
        team_id="T-audit",
        user_id="U123456",
        channel_id="C-audit",
        thread_ts="123.456",
        event_type="app_mention",
        text="health",
    )


def test_record_is_utc_json_and_default_deny_projection(
    caplog: pytest.LogCaptureFixture,
) -> None:
    canaries = {
        "payload": "raw-slack-body-canary",
        "x-slack-request-timestamp": "slack-header-canary",
        "x-slack-signature": "signature-canary",
        "token": "bot-token-canary",
        "api_key": "api-key-canary",
        "kubeconfig": "kubeconfig-canary",
        "filename": "private-document-canary.pdf",
        "rag_document": "rag-document-content-canary",
        "mcp_response": "mcp-response-canary",
        "kubernetes_response": "kubernetes-response-canary",
        "exception": "provider-exception-canary",
    }
    caplog.set_level(logging.INFO, logger="chatops-bot.audit")

    log_tool_call(
        user="not-a-slack-id-secret-canary",
        tool="not-an-allowlisted-tool-secret-canary",
        args=canaries,
        result_summary="rag-text-secret-canary",
        approved=False,
    )

    record = json.loads(caplog.records[-1].message)
    assert set(record) == {
        "timestamp",
        "event_id",
        "run_id",
        "user",
        "action",
        "tool",
        "decision",
        "approval",
        "summary",
        "test_run_id",
    }
    assert record["decision"] == "denied"
    assert record["user"] == "unknown"
    assert record["tool"] == "unknown"
    assert record["summary"] == "sanitized"
    assert record["approval"] == {"state": "not_required"}
    assert datetime.fromisoformat(record["timestamp"].replace("Z", "+00:00")).tzinfo is not None
    for canary in (*canaries.values(), "rag-text-secret-canary", "not-a-slack-id-secret-canary"):
        assert canary not in caplog.text


def test_verifier_observations_are_fresh_and_correlated(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    output = tmp_path / "observations.json"
    monkeypatch.setenv("INSIGHTHUB_VERIFY_RUN_ID", "verify-run-123")
    monkeypatch.setenv("INSIGHTHUB_VERIFY_OBSERVATIONS", str(output))

    log_audit_event(
        event_id=event().identity,
        run_id=event().run_id,
        user=event().user_id,
        action="insighthub_health",
        tool="mcp.insighthub_health",
        decision="allowed",
        approval_state="not_required",
        summary="mcp_success",
    )

    observations = json.loads(output.read_text(encoding="utf-8"))
    assert observations["run_id"] == "verify-run-123"
    assert len(observations["events"]) == 1
    assert observations["events"][0]["run_id"] == event().run_id
    assert observations["events"][0]["test_run_id"] == "verify-run-123"


def test_read_only_tool_is_not_called_when_file_sink_is_unavailable(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("CHATOPS_AUDIT_SINK", "file")
    monkeypatch.setenv("CHATOPS_AUDIT_FILE", str(tmp_path / "missing" / "audit.jsonl"))
    get_settings.cache_clear()
    called = False

    async def operation() -> dict[str, object]:
        nonlocal called
        called = True
        return {"live": True, "ready": True, "databaseReady": True}

    pending = operation()
    with pytest.raises(AuditUnavailable):
        run(
            intents._call(
                event(),
                "insighthub_health",
                "mcp.insighthub_health",
                pending,
                lambda value: value,
            )
        )
    pending.close()
    assert called is False
