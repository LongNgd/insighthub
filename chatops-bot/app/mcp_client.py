"""Fixed local STDIO MCP calls for the ChatOps worker.

The worker launches a source-owned Node bridge with no shell and no stdin.
Slack text therefore cannot choose an executable, MCP server, tool, namespace,
or tool arguments. The bridge starts the pinned local MCP packages itself.
"""

import asyncio
import json
import math
import os
import re
from collections.abc import Mapping
from datetime import date as calendar_date, timedelta
from pathlib import Path
from typing import Protocol

from app.config import Settings, get_settings
from app.errors import McpSchemaError, McpUnavailable


REQUESTS_5M = "requests_5m"
ERRORS_5M = "errors_5m"
_NODE_EXECUTABLE = "node"
_BRIDGE_PATH = (
    Path(__file__).resolve().parents[2] / "tools" / "mcp" / "src" / "chatops-stdio.mjs"
)
_CAPABILITIES = frozenset(
    {
        "health",
        "requests_5m",
        "errors_5m",
        "ingest_count_today_utc",
        "pods_in_configured_namespace",
    }
)


class ReadOnlyMcpClient(Protocol):
    """The only capabilities available to the intent router."""

    async def health(self) -> Mapping[str, object]: ...

    async def prometheus_requests_5m(self) -> Mapping[str, object]: ...

    async def prometheus_errors_5m(self) -> Mapping[str, object]: ...

    async def ingest_count_today_utc(self) -> Mapping[str, object]: ...

    async def pods(self) -> Mapping[str, object]: ...


class StdioReadOnlyMcpClient:
    """Expose fixed worker capabilities through the local source-owned bridge."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def health(self) -> Mapping[str, object]:
        return await _run_stdio_capability(self._settings, "health")

    async def prometheus_requests_5m(self) -> Mapping[str, object]:
        return await _run_stdio_capability(self._settings, "requests_5m")

    async def prometheus_errors_5m(self) -> Mapping[str, object]:
        return await _run_stdio_capability(self._settings, "errors_5m")

    async def ingest_count_today_utc(self) -> Mapping[str, object]:
        return await _run_stdio_capability(self._settings, "ingest_count_today_utc")

    async def pods(self) -> Mapping[str, object]:
        return await _run_stdio_capability(
            self._settings, "pods_in_configured_namespace"
        )


def get_readonly_mcp_client() -> ReadOnlyMcpClient:
    """Create a per-job local STDIO client; configuration remains operator-owned."""

    return StdioReadOnlyMcpClient(get_settings())


async def _run_stdio_capability(
    settings: Settings, capability: str
) -> Mapping[str, object]:
    """Run exactly one bridge capability with bounded output and no shell."""

    if capability not in _CAPABILITIES or not _BRIDGE_PATH.is_file():
        raise McpUnavailable()
    try:
        process = await asyncio.create_subprocess_exec(
            _NODE_EXECUTABLE,
            str(_BRIDGE_PATH),
            capability,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
            env=_bridge_environment(settings),
        )
    except OSError as error:
        raise McpUnavailable() from error
    try:
        payload, return_code = await asyncio.wait_for(
            _collect_bridge_output(process, settings.mcp_max_response_bytes),
            timeout=settings.mcp_timeout_seconds,
        )
    except TimeoutError as error:
        await _stop_process(process)
        raise McpUnavailable() from error
    except McpSchemaError:
        await _stop_process(process)
        raise
    if return_code != 0:
        raise McpUnavailable()
    return _bridge_result(payload)


def _bridge_environment(settings: Settings) -> dict[str, str]:
    """Pass only non-secret, fixed bridge configuration to child processes."""

    return {
        "PATH": os.environ.get("PATH", ""),
        "CHATOPS_INSIGHTHUB_API_URL": settings.insighthub_api_url,
        "CHATOPS_PROMETHEUS_URL": settings.prometheus_url,
        "CHATOPS_KUBERNETES_KUBECONFIG": settings.kubernetes_kubeconfig,
        "CHATOPS_KUBERNETES_NAMESPACE": settings.kubernetes_namespace,
    }


async def _collect_bridge_output(
    process: asyncio.subprocess.Process, maximum: int
) -> tuple[bytes, int]:
    if process.stdout is None:
        raise McpUnavailable()
    body = bytearray()
    while chunk := await process.stdout.read(4096):
        body.extend(chunk)
        if len(body) > maximum:
            raise McpSchemaError()
    return bytes(body), await process.wait()


async def _stop_process(process: asyncio.subprocess.Process) -> None:
    if process.returncode is None:
        process.kill()
        await process.wait()


def _bridge_result(payload: bytes) -> Mapping[str, object]:
    """Accept a single sanitized bridge envelope and discard all error detail."""

    try:
        decoded = json.loads(payload)
    except (TypeError, ValueError) as error:
        raise McpSchemaError() from error
    if not isinstance(decoded, dict) or decoded.get("ok") is not True:
        if isinstance(decoded, dict) and decoded.get("category") == "unavailable":
            raise McpUnavailable()
        raise McpSchemaError()
    result = decoded.get("result")
    if not isinstance(result, dict):
        raise McpSchemaError()
    return result


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
        or len(phase) > 32
    ):
        raise McpSchemaError()
    containers = status.get("containerStatuses")
    if not isinstance(containers, list) or len(containers) > 50:
        raise McpSchemaError()
    restart_count = 0
    reasons: set[str] = set()
    for container in containers:
        if not isinstance(container, dict):
            raise McpSchemaError()
        restarts = container.get("restartCount")
        state = container.get("state")
        if isinstance(restarts, bool) or not isinstance(restarts, int) or restarts < 0:
            raise McpSchemaError()
        if not isinstance(state, dict):
            raise McpSchemaError()
        restart_count += restarts
        for state_name, known_reasons in (
            ("waiting", _WAITING_REASONS),
            ("terminated", _TERMINATED_REASONS),
        ):
            state_value = state.get(state_name)
            if state_value is None:
                continue
            if not isinstance(state_value, dict):
                raise McpSchemaError()
            reason = state_value.get("reason")
            if reason in known_reasons:
                reasons.add(reason)
    if phase in {"Failed", "Unknown"}:
        reasons.add(f"phase={phase}")
    if restart_count >= restart_threshold:
        reasons.add(f"restarts>={restart_threshold}")
    if not reasons:
        return None
    return (
        f"pod={name}, phase={phase}, restarts={restart_count}, "
        f"reasons={','.join(sorted(reasons))}"
    )
