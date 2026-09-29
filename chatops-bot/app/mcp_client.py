"""Fixed read-only MCP calls for the ChatOps worker.

This module intentionally exposes capability methods rather than a generic
``call_tool`` API.  The Slack event text cannot select an endpoint, tool,
namespace, headers, or arguments.
"""

import asyncio
import json
import math
import re
from collections.abc import Mapping
from datetime import date as calendar_date, timedelta
from typing import Protocol
from uuid import uuid4

import httpx

from app.config import Settings, get_settings
from app.errors import McpSchemaError, McpUnavailable


INSIGHTHUB_HEALTH_TOOL = "insighthub_health"
INSIGHTHUB_INGEST_COUNT_TOOL = "insighthub_ingest_count_today_utc"
PROMETHEUS_SUMMARY_TOOL = "prometheus_summary"
KUBERNETES_PODS_TOOL = "get_pods"
REQUESTS_5M = "requests_5m"
ERRORS_5M = "errors_5m"


class ReadOnlyMcpClient(Protocol):
    """The only capabilities available to the intent router."""

    async def health(self) -> Mapping[str, object]: ...

    async def prometheus_requests_5m(self) -> Mapping[str, object]: ...

    async def prometheus_errors_5m(self) -> Mapping[str, object]: ...

    async def ingest_count_today_utc(self) -> Mapping[str, object]: ...

    async def pods(self) -> Mapping[str, object]: ...


class HttpReadOnlyMcpClient:
    """Minimal bounded JSON-RPC client for operator-configured MCP transports."""

    def __init__(
        self, settings: Settings, transport: httpx.AsyncBaseTransport | None = None
    ) -> None:
        self._settings = settings
        self._transport = transport

    async def health(self) -> Mapping[str, object]:
        return await self._insighthub_call(INSIGHTHUB_HEALTH_TOOL, {})

    async def prometheus_requests_5m(self) -> Mapping[str, object]:
        return await self._insighthub_call(
            PROMETHEUS_SUMMARY_TOOL, {"query": REQUESTS_5M}
        )

    async def prometheus_errors_5m(self) -> Mapping[str, object]:
        return await self._insighthub_call(
            PROMETHEUS_SUMMARY_TOOL, {"query": ERRORS_5M}
        )

    async def ingest_count_today_utc(self) -> Mapping[str, object]:
        return await self._insighthub_call(INSIGHTHUB_INGEST_COUNT_TOOL, {})

    async def pods(self) -> Mapping[str, object]:
        return await self._call(
            endpoint=self._settings.kubernetes_mcp_url,
            bearer_token=self._settings.kubernetes_mcp_bearer_token,
            tool=KUBERNETES_PODS_TOOL,
            arguments={"namespace": self._settings.kubernetes_namespace},
        )

    async def _insighthub_call(
        self, tool: str, arguments: Mapping[str, object]
    ) -> Mapping[str, object]:
        return await self._call(
            endpoint=self._settings.insighthub_mcp_url,
            bearer_token=self._settings.insighthub_mcp_bearer_token,
            tool=tool,
            arguments=arguments,
        )

    async def _call(
        self,
        *,
        endpoint: str,
        bearer_token: str,
        tool: str,
        arguments: Mapping[str, object],
    ) -> Mapping[str, object]:
        url = _mcp_endpoint(endpoint)
        headers = {"Accept": "application/json", "Content-Type": "application/json"}
        if bearer_token:
            headers["Authorization"] = f"Bearer {bearer_token}"
        payload = {
            "jsonrpc": "2.0",
            "id": str(uuid4()),
            "method": "tools/call",
            "params": {"name": tool, "arguments": dict(arguments)},
        }
        timeout = self._settings.mcp_timeout_seconds
        try:
            async with httpx.AsyncClient(
                timeout=timeout,
                follow_redirects=False,
                transport=self._transport,
            ) as client:
                async with client.stream(
                    "POST", url, headers=headers, json=payload
                ) as response:
                    if response.status_code >= 500 or response.status_code == 429:
                        raise McpUnavailable()
                    if response.status_code < 200 or response.status_code >= 300:
                        raise McpSchemaError()
                    content_length = response.headers.get("content-length")
                    if content_length is not None and _invalid_length(
                        content_length, self._settings.mcp_max_response_bytes
                    ):
                        raise McpSchemaError()
                    body = bytearray()
                    async for chunk in response.aiter_bytes():
                        body.extend(chunk)
                        if len(body) > self._settings.mcp_max_response_bytes:
                            raise McpSchemaError()
        except McpSchemaError:
            raise
        except (httpx.TimeoutException, httpx.RequestError) as error:
            raise McpUnavailable() from error
        try:
            decoded = json.loads(body)
        except (TypeError, ValueError) as error:
            raise McpSchemaError() from error
        return _structured_content(decoded)


def get_readonly_mcp_client() -> ReadOnlyMcpClient:
    """Create a per-job client; endpoints and credentials stay operator-owned."""

    return HttpReadOnlyMcpClient(get_settings())


def _mcp_endpoint(value: str) -> str:
    """Validate an operator endpoint without permitting user-supplied routing."""

    try:
        url = httpx.URL(value)
    except Exception as error:
        raise McpUnavailable() from error
    if (
        url.scheme not in {"http", "https"}
        or not url.host
        or url.userinfo
        or url.query
        or url.fragment
    ):
        raise McpUnavailable()
    return str(url)


def _invalid_length(value: str, maximum: int) -> bool:
    try:
        return int(value) > maximum or int(value) < 0
    except ValueError:
        return True


def _structured_content(payload: object) -> Mapping[str, object]:
    """Extract only structured MCP tool content and never surface provider errors."""

    if not isinstance(payload, dict) or "error" in payload:
        raise McpSchemaError()
    result = payload.get("result")
    if not isinstance(result, dict) or result.get("isError") is True:
        raise McpSchemaError()
    content = result.get("structuredContent")
    if not isinstance(content, dict):
        raise McpSchemaError()
    return content


def validate_health(value: Mapping[str, object]) -> tuple[bool, bool, bool]:
    """Validate the custom MCP health projection exactly enough for triage."""

    fields = (value.get("live"), value.get("ready"), value.get("databaseReady"))
    if not all(isinstance(item, bool) for item in fields):
        raise McpSchemaError()
    return fields[0], fields[1], fields[2]


def validate_metric(value: Mapping[str, object], expected_query: str) -> float | None:
    """Accept one finite aggregate from the fixed Prometheus query identifier."""

    if value.get("query") != expected_query or value.get("window") != "5m":
        raise McpSchemaError()
    metric = value.get("value")
    if metric is None:
        return None
    if isinstance(metric, bool) or not isinstance(metric, (int, float)):
        raise McpSchemaError()
    number = float(metric)
    if not math.isfinite(number) or number < 0:
        raise McpSchemaError()
    return number


def validate_ingest_count(value: Mapping[str, object]) -> tuple[str, int]:
    """Keep only a valid current-day count and the date it belongs to."""

    date = value.get("date_utc")
    start = value.get("interval_start_utc")
    end = value.get("interval_end_utc")
    count = value.get("count")
    if (
        not isinstance(date, str)
        or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date)
        or start != f"{date}T00:00:00Z"
        or not isinstance(end, str)
        or not re.fullmatch(r"\d{4}-\d{2}-\d{2}T00:00:00Z", end)
        or isinstance(count, bool)
        or not isinstance(count, int)
        or count < 0
    ):
        raise McpSchemaError()
    try:
        expected_end = (calendar_date.fromisoformat(date) + timedelta(days=1)).isoformat()
    except ValueError as error:
        raise McpSchemaError() from error
    if end != f"{expected_end}T00:00:00Z":
        raise McpSchemaError()
    return date, count


_POD_NAME = re.compile(r"[a-z0-9](?:[-.a-z0-9]{0,251}[a-z0-9])?")
_WAITING_REASONS = frozenset(
    {
        "CrashLoopBackOff",
        "ImagePullBackOff",
        "ErrImagePull",
        "CreateContainerConfigError",
        "CreateContainerError",
        "RunContainerError",
    }
)
_TERMINATED_REASONS = frozenset({"Error", "OOMKilled", "ContainerCannotRun"})


def summarize_abnormal_pods(
    value: Mapping[str, object], *, restart_threshold: int, maximum: int
) -> list[str]:
    """Project bounded K8s pod status into safe, actionable triage facts."""

    items = value.get("items")
    if not isinstance(items, list) or len(items) > 100:
        raise McpSchemaError()
    summaries: list[str] = []
    for item in items:
        finding = _pod_finding(item, restart_threshold)
        if finding is not None:
            summaries.append(finding)
            if len(summaries) == maximum:
                break
    return summaries


def _pod_finding(item: object, restart_threshold: int) -> str | None:
    if not isinstance(item, dict):
        raise McpSchemaError()
    metadata = item.get("metadata")
    status = item.get("status")
    if not isinstance(metadata, dict) or not isinstance(status, dict):
        raise McpSchemaError()
    name = metadata.get("name")
    phase = status.get("phase")
    if (
        not isinstance(name, str)
        or not _POD_NAME.fullmatch(name)
        or not isinstance(phase, str)
    ):
        raise McpSchemaError()
    reasons: set[str] = set()
    if phase in {"Failed", "Unknown"}:
        reasons.add(phase.lower())
    conditions = status.get("conditions", [])
    if not isinstance(conditions, list):
        raise McpSchemaError()
    for condition in conditions:
        if not isinstance(condition, dict):
            raise McpSchemaError()
        if condition.get("type") == "Ready" and condition.get("status") != "True":
            reasons.add("not_ready")
    restarts = 0
    for statuses_key in ("initContainerStatuses", "containerStatuses"):
        statuses = status.get(statuses_key, [])
        if not isinstance(statuses, list):
            raise McpSchemaError()
        for container in statuses:
            if not isinstance(container, dict):
                raise McpSchemaError()
            restart_count = container.get("restartCount", 0)
            if isinstance(restart_count, bool) or not isinstance(restart_count, int) or restart_count < 0:
                raise McpSchemaError()
            restarts += restart_count
            state = container.get("state", {})
            if not isinstance(state, dict):
                raise McpSchemaError()
            waiting = state.get("waiting")
            terminated = state.get("terminated")
            if waiting is not None:
                if not isinstance(waiting, dict):
                    raise McpSchemaError()
                reason = waiting.get("reason")
                if reason in _WAITING_REASONS:
                    reasons.add(str(reason))
            if terminated is not None:
                if not isinstance(terminated, dict):
                    raise McpSchemaError()
                reason = terminated.get("reason")
                if reason in _TERMINATED_REASONS:
                    reasons.add(str(reason))
    if restarts >= restart_threshold:
        reasons.add(f"restarts>={restart_threshold}")
    if not reasons:
        return None
    safe_reasons = ",".join(sorted(reasons))
    return f"pod={name}, phase={phase}, restarts={restarts}, reasons={safe_reasons}"
