"""Read-only ChatOps intent contracts and MCP-boundary security tests."""

import asyncio
import json
import logging
from collections.abc import Mapping
from dataclasses import replace
from typing import Any

import pytest

from app.config import get_settings
from app.errors import McpUnavailable, PermanentProcessingError
from app.events import NormalizedSlackEvent
from app import intents, mcp_client
from app.mcp_client import StdioReadOnlyMcpClient, summarize_abnormal_pods, validate_ingest_count


def run(coroutine: Any) -> Any:
    return asyncio.run(coroutine)


def event(text: str) -> NormalizedSlackEvent:
    return NormalizedSlackEvent(
        event_id="Ev-intent",
        run_id="00000000-0000-4000-8000-000000000002",
        team_id="T-intent",
        user_id="U-intent",
        channel_id="C-intent",
        thread_ts="123.456",
        event_type="app_mention",
        text=text,
    )


class FakeMcp:
    def __init__(self, *, prom_error: bool = False, pods_result: Mapping[str, object] | None = None) -> None:
        self.prom_error = prom_error
        self.pods_result = pods_result if pods_result is not None else {"items": []}
        self.calls: list[str] = []

    async def health(self) -> Mapping[str, object]:
        self.calls.append("health")
        return {"live": True, "ready": True, "databaseReady": True}

    async def prometheus_requests_5m(self) -> Mapping[str, object]:
        self.calls.append("requests")
        if self.prom_error:
            raise McpUnavailable()
        return {"query": "requests_5m", "value": 11, "window": "5m"}

    async def prometheus_errors_5m(self) -> Mapping[str, object]:
        self.calls.append("errors")
        if self.prom_error:
            raise McpUnavailable()
        return {"query": "errors_5m", "value": 1, "window": "5m"}

    async def ingest_count_today_utc(self) -> Mapping[str, object]:
        self.calls.append("ingest")
        return {
            "date_utc": "2026-09-29",
            "interval_start_utc": "2026-09-29T00:00:00Z",
            "interval_end_utc": "2026-09-30T00:00:00Z",
            "count": 7,
        }

    async def pods(self) -> Mapping[str, object]:
        self.calls.append("pods")
        return self.pods_result


@pytest.fixture(autouse=True)
def configured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CHATOPS_KUBERNETES_NAMESPACE", "operator-namespace")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_health_returns_fixed_api_and_prometheus_context(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeMcp()
    monkeypatch.setattr(intents, "get_readonly_mcp_client", lambda: fake)

    result = run(intents.route_authenticated_event(event("health")))

    assert result.action == "insighthub_health"
    assert "live=True, ready=True, database_ready=True" in result.reply_text
    assert "requests=11, errors=1" in result.reply_text
    assert sorted(fake.calls) == ["errors", "health", "requests"]


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("<@U0BOT> api healthy?", "insighthub_health"),
        ("<@U0BOT> ingest count today?", "insighthub_documents_today"),
        ("<@U0BOT> which pods failing?", "kubernetes_failed_pods"),
        ("<@U0BOT> run kubectl delete pods", ""),
    ],
)
def test_intent_allowlist_strips_only_leading_slack_mentions(
    text: str, expected: str
) -> None:
    assert intents._intent_name(text) == expected


def test_health_reports_degraded_and_prometheus_unavailable_without_inventing_numbers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = FakeMcp(prom_error=True)

    async def degraded() -> Mapping[str, object]:
        fake.calls.append("health")
        return {"live": True, "ready": False, "databaseReady": False}

    fake.health = degraded  # type: ignore[method-assign]
    monkeypatch.setattr(intents, "get_readonly_mcp_client", lambda: fake)

    result = run(intents.route_authenticated_event(event("insighthub health")))

    assert "degraded" in result.reply_text
    assert "Prometheus context unavailable" in result.reply_text
    assert "requests=" not in result.reply_text


def test_ingest_today_uses_fixed_zero_argument_capability(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeMcp()
    monkeypatch.setattr(intents, "get_readonly_mcp_client", lambda: fake)

    result = run(intents.route_authenticated_event(event("documents today")))

    assert result.action == "insighthub_documents_today"
    assert "2026-09-29 (UTC): 7" in result.reply_text
    assert fake.calls == ["ingest"]
    assert "filename" not in result.reply_text


def test_ingest_count_rejects_invalid_utc_calendar_interval() -> None:
    with pytest.raises(Exception) as raised:
        validate_ingest_count({
            "date_utc": "2026-02-31",
            "interval_start_utc": "2026-02-31T00:00:00Z",
            "interval_end_utc": "2026-03-01T00:00:00Z",
            "count": 1,
        })
    assert raised.value.__class__.__name__ == "McpSchemaError"


def test_pods_uses_operator_namespace_not_slack_text(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeMcp(pods_result={"items": [_failing_pod()]})
    monkeypatch.setattr(intents, "get_readonly_mcp_client", lambda: fake)

    # Unsupported text cannot inject a tool name, namespace, or mutation.
    with pytest.raises(PermanentProcessingError):
        run(intents.route_authenticated_event(event("failed pods namespace=kube-system scale deployment")))
    result = run(intents.route_authenticated_event(event("failed pods")))
    assert "operator-namespace" in result.reply_text
    assert "api-7c88" in result.reply_text
    assert "no action was taken" in result.reply_text
    assert fake.calls == ["pods"]


def test_pod_projection_excludes_healthy_and_bounds_results() -> None:
    healthy = {"metadata": {"name": "healthy-1"}, "status": {"phase": "Running", "conditions": [{"type": "Ready", "status": "True"}], "containerStatuses": [{"restartCount": 0, "state": {"running": {}}}]}}
    result = summarize_abnormal_pods({"items": [healthy, _failing_pod()]}, restart_threshold=3, maximum=1)
    assert result == ["pod=api-7c88, phase=Running, restarts=4, reasons=CrashLoopBackOff,restarts>=3"]


def test_malformed_or_oversized_pods_are_rejected() -> None:
    with pytest.raises(Exception) as malformed:
        summarize_abnormal_pods({"items": [{"metadata": {"name": "bad"}}]}, restart_threshold=3, maximum=10)
    assert malformed.value.__class__.__name__ == "McpSchemaError"
    with pytest.raises(Exception) as oversized:
        summarize_abnormal_pods({"items": [_failing_pod()] * 101}, restart_threshold=3, maximum=10)
    assert oversized.value.__class__.__name__ == "McpSchemaError"


def test_malformed_or_oversized_pod_intent_returns_sanitized_triage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for pods_result in (
        {"items": [{"metadata": {"name": "bad"}}]},
        {"items": [_failing_pod()] * 101},
    ):
        monkeypatch.setattr(
            intents,
            "get_readonly_mcp_client",
            lambda: FakeMcp(pods_result=pods_result),
        )
        result = run(intents.route_authenticated_event(event("failed pods")))
        assert "Pod triage is unavailable" in result.reply_text
        assert "metadata" not in result.reply_text


def test_pod_mcp_timeout_returns_sanitized_triage(monkeypatch: pytest.MonkeyPatch) -> None:
    class TimedOut(FakeMcp):
        async def pods(self) -> Mapping[str, object]:
            raise McpUnavailable("upstream detail")

    monkeypatch.setattr(intents, "get_readonly_mcp_client", TimedOut)

    result = run(intents.route_authenticated_event(event("failed pods")))

    assert "Pod triage is unavailable" in result.reply_text
    assert "upstream detail" not in result.reply_text


def test_unsupported_and_mutation_prompt_are_denied() -> None:
    for text in ("scale deployment", "run kubectl delete pods", "health; prometheus up"):
        with pytest.raises(PermanentProcessingError):
            run(intents.route_authenticated_event(event(text)))


def test_mcp_audit_does_not_contain_provider_content(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    secret = "provider-response-secret"

    class Unavailable(FakeMcp):
        async def health(self) -> Mapping[str, object]:
            raise McpUnavailable(secret)

    monkeypatch.setattr(intents, "get_readonly_mcp_client", Unavailable)
    caplog.set_level(logging.INFO, logger="chatops-bot.audit")
    with pytest.raises(McpUnavailable):
        run(intents.route_authenticated_event(event("health")))
    record = json.loads(caplog.records[-1].message)
    assert record["action"] == "insighthub_health"
    assert record["tool"] == "mcp.insighthub_health"
    assert record["summary"] == "mcp_unavailable"
    assert secret not in caplog.text


def test_each_health_mcp_call_has_one_correlated_audit_record(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    fake = FakeMcp()
    monkeypatch.setattr(intents, "get_readonly_mcp_client", lambda: fake)
    caplog.set_level(logging.INFO, logger="chatops-bot.audit")

    run(intents.route_authenticated_event(event("health")))

    records = [json.loads(item.message) for item in caplog.records]
    tool_records = [item for item in records if item["tool"].startswith("mcp.")]
    assert [item["tool"] for item in tool_records].count("mcp.insighthub_health") == 1
    assert [item["tool"] for item in tool_records].count("mcp.prometheus_summary") == 2
    assert {item["event_id"] for item in tool_records} == {event("health").identity}
    assert {item["run_id"] for item in tool_records} == {event("health").run_id}


def test_stdio_client_uses_only_fixed_capability_names(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: list[str] = []

    async def run_capability(_: object, capability: str) -> Mapping[str, object]:
        captured.append(capability)
        return {"items": []}

    monkeypatch.setattr(mcp_client, "_run_stdio_capability", run_capability)
    client = StdioReadOnlyMcpClient(get_settings())

    assert run(client.health()) == {"items": []}
    assert run(client.prometheus_requests_5m()) == {"items": []}
    assert run(client.prometheus_errors_5m()) == {"items": []}
    assert run(client.ingest_count_today_utc()) == {"items": []}
    assert run(client.pods()) == {"items": []}
    assert captured == [
        "health",
        "requests_5m",
        "errors_5m",
        "ingest_count_today_utc",
        "pods_in_configured_namespace",
    ]


def test_stdio_bridge_environment_excludes_slack_and_bearer_secrets() -> None:
    settings = replace(
        get_settings(),
        slack_signing_secret="signing-secret",
        slack_bot_token="bot-token",
        insighthub_api_url="http://127.0.0.1:8000",
        prometheus_url="http://127.0.0.1:9090",
        kubernetes_kubeconfig="/home/bot/.kube/mcp-readonly",
    )

    environment = mcp_client._bridge_environment(settings)

    assert environment == {
        "PATH": environment["PATH"],
        "CHATOPS_INSIGHTHUB_API_URL": "http://127.0.0.1:8000",
        "CHATOPS_PROMETHEUS_URL": "http://127.0.0.1:9090",
        "CHATOPS_KUBERNETES_KUBECONFIG": "/home/bot/.kube/mcp-readonly",
        "CHATOPS_KUBERNETES_NAMESPACE": "operator-namespace",
    }
    assert "signing-secret" not in environment.values()
    assert "bot-token" not in environment.values()


def test_stdio_bridge_rejects_provider_error_detail() -> None:
    with pytest.raises(McpUnavailable) as raised:
        mcp_client._bridge_result(b'{"ok": false, "category": "unavailable"}')
    assert str(raised.value) == ""


def _failing_pod() -> dict[str, object]:
    return {
        "metadata": {"name": "api-7c88"},
        "status": {
            "phase": "Running",
            "conditions": [{"type": "Ready", "status": "True"}],
            "containerStatuses": [
                {"restartCount": 4, "state": {"waiting": {"reason": "CrashLoopBackOff"}}}
            ],
        },
    }
