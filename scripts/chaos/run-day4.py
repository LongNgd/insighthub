#!/usr/bin/env python3
"""Bounded local-kind fixture traffic with unsilenced anomaly notifications."""

import argparse
import json
import subprocess
import sys
import time
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen

CONTEXT = "kind-insighthub"
NAMESPACE = "insighthub-prod"
CONTROL = "insighthub-day4-chaos"
ALERTS = {
    "latency": "InsightHubLLMLatencyAnomaly",
    "backlog": "InsightHubQueueDepthAnomaly",
    "errors": "InsightHubHTTP5xxAnomaly",
}
SIGNALS = (
    "llm_latency_p95_seconds",
    "queue_entries",
    "http_5xx_percent",
)
FIXTURE_TEXT = b"InsightHub Day 4 fixture document. The worker stores this short test text.\n"


def utc_now() -> datetime:
    return datetime.now(UTC)


def stamp(value: datetime) -> str:
    return value.isoformat(timespec="seconds").replace("+00:00", "Z")


def local_url(value: str) -> str:
    parsed = urlsplit(value)
    if parsed.scheme != "http" or parsed.hostname not in {"localhost", "127.0.0.1"}:
        raise ValueError("Endpoints must use an HTTP localhost port-forward")
    return value.rstrip("/")


def json_request(url: str, *, payload: dict | None = None) -> tuple[int, dict | list]:
    data = None if payload is None else json.dumps(payload).encode()
    request = Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"} if data is not None else {},
        method="POST" if data is not None else "GET",
    )
    try:
        with urlopen(request, timeout=15) as response:
            return response.status, json.load(response)
    except Exception as exc:
        from urllib.error import HTTPError

        if isinstance(exc, HTTPError):
            # A fixture 502 has a fixed public error contract; never print its body.
            return exc.code, {}
        raise RuntimeError("Local port-forward request failed") from None


def prom_query(prometheus_url: str, expression: str) -> list[dict]:
    _, body = json_request(prometheus_url + "/api/v1/query?" + urlencode({"query": expression}))
    if not isinstance(body, dict) or body.get("status") != "success":
        raise RuntimeError("Prometheus query failed")
    return body["data"]["result"]


def current_alerts(prometheus_url: str) -> dict[str, str]:
    _, body = json_request(prometheus_url + "/api/v1/alerts")
    if not isinstance(body, dict) or body.get("status") != "success":
        raise RuntimeError("Prometheus alerts query failed")
    return {
        alert["labels"]["alertname"]: alert["state"]
        for alert in body["data"]["alerts"]
        if alert.get("labels", {}).get("namespace") == NAMESPACE
        and alert.get("labels", {}).get("alertname") in ALERTS.values()
    }


def preflight(prometheus_url: str) -> None:
    for signal in SIGNALS:
        prefix = f"insighthub:{signal}"
        for suffix, expected in (("current", None), ("baseline_ready", 1), ("band_upper", None)):
            rows = prom_query(prometheus_url, f'{prefix}:{suffix}{{namespace="{NAMESPACE}"}}')
            if len(rows) != 1 or (expected is not None and float(rows[0]["value"][1]) != expected):
                raise RuntimeError(f"Preflight failed: {signal}:{suffix}")
    targets = prom_query(prometheus_url, f'up{{namespace="{NAMESPACE}"}}')
    if len(targets) < 5 or any(float(row["value"][1]) != 1 for row in targets):
        raise RuntimeError("Preflight failed: five InsightHub scrape targets must be UP")
    if current_alerts(prometheus_url):
        raise RuntimeError("Preflight failed: anomaly alerts must be inactive")


def ensure_no_active_silences(alertmanager_url: str) -> None:
    status, silences = json_request(alertmanager_url + "/api/v2/silences")
    if status != 200 or not isinstance(silences, list):
        raise RuntimeError("Alertmanager silence query failed")
    if any(silence.get("status", {}).get("state") == "active" for silence in silences):
        raise RuntimeError("Active Alertmanager silence present; notification delivery is not guaranteed")


def set_fault(mode: str, delay_seconds: int, expires_at: datetime | None = None) -> None:
    config = {
        "mode": mode,
        "delay_seconds": delay_seconds,
        "expires_at": stamp(expires_at or datetime(1970, 1, 1, tzinfo=UTC)),
    }
    patch = json.dumps({"data": {"fault.json": json.dumps(config, separators=(",", ":"))}})
    result = subprocess.run(
        [
            "kubectl", "--context", CONTEXT, "-n", NAMESPACE, "patch", "configmap", CONTROL,
            "--type=merge", "-p", patch,
        ],
        capture_output=True, text=True, timeout=20, check=False,
    )
    if result.returncode:
        raise RuntimeError("Could not update Day 4 fixture control ConfigMap")


def ensure_ready_document(api_url: str) -> None:
    status, documents = json_request(api_url + "/documents")
    if status != 200 or not isinstance(documents, list):
        raise RuntimeError("Could not list documents")
    if not any(document.get("status") == "ready" for document in documents):
        raise RuntimeError("A ready fixture document is required for chat traffic")


def chat_traffic(api_url: str, prometheus_url: str, seconds: int, mode: str) -> dict:
    observations: dict[str, str] = {}
    counts: dict[str, int] = {}
    deadline = time.monotonic() + seconds
    next_call = time.monotonic()
    while time.monotonic() < deadline:
        status, _ = json_request(api_url + "/chat", payload={"question": "Summarize the Day 4 fixture."})
        counts[str(status)] = counts.get(str(status), 0) + 1
        state = current_alerts(prometheus_url)
        alertname = ALERTS.get(mode)
        if alertname is not None and state.get(alertname) in {"pending", "firing"}:
            observations.setdefault(state[alertname], stamp(utc_now()))
        next_call += 60 if mode == "baseline" else 10
        time.sleep(max(0, min(next_call - time.monotonic(), deadline - time.monotonic())))
    return {"responses": counts, "alert_transitions": observations}


def backlog_traffic(api_url: str, prometheus_url: str, seconds: int) -> dict:
    accepted: list[int] = []
    for index in range(30):
        boundary = "day4fixture"
        body = (
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; "
            f"filename=\"day4-backlog-{index:02d}.txt\"\r\n"
            "Content-Type: text/plain\r\n\r\n"
        ).encode() + FIXTURE_TEXT + f"\r\n--{boundary}--\r\n".encode()
        request = Request(
            api_url + "/documents", data=body,
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"}, method="POST",
        )
        with urlopen(request, timeout=15) as response:
            if response.status != 202:
                raise RuntimeError("Fixture upload did not return 202")
            accepted.append(json.load(response)["id"])
        time.sleep(0.5)
    observations: dict[str, str] = {}
    deadline = time.monotonic() + seconds
    next_chat = time.monotonic()
    while time.monotonic() < deadline:
        # Keep the independent latency baseline populated while the worker is
        # deliberately slow; the backlog fault does not affect fixture chat.
        if time.monotonic() >= next_chat:
            json_request(api_url + "/chat", payload={"question": "Summarize the Day 4 fixture."})
            next_chat = time.monotonic() + 60
        state = current_alerts(prometheus_url).get(ALERTS["backlog"])
        if state in {"pending", "firing"}:
            observations.setdefault(state, stamp(utc_now()))
        time.sleep(min(10, max(0, deadline - time.monotonic())))
    return {"accepted_document_ids": accepted, "alert_transitions": observations}


def wait_recovery(api_url: str, prometheus_url: str, mode: str) -> str:
    signal = {"latency": SIGNALS[0], "backlog": SIGNALS[1], "errors": SIGNALS[2]}[mode]
    normal_ceiling = {"latency": 0.5, "backlog": 2.0, "errors": 2.0}[mode]
    deadline = time.monotonic() + 15 * 60
    next_chat = 0.0
    while time.monotonic() < deadline:
        if mode != "backlog" and time.monotonic() >= next_chat:
            json_request(api_url + "/chat", payload={"question": "Summarize the Day 4 fixture."})
            next_chat = time.monotonic() + 60
        current = prom_query(
            prometheus_url, f'insighthub:{signal}:current{{namespace="{NAMESPACE}"}}',
        )
        upper = prom_query(
            prometheus_url, f'insighthub:{signal}:band_upper{{namespace="{NAMESPACE}"}}',
        )
        if (
            len(current) == len(upper) == 1
            and float(current[0]["value"][1]) <= float(upper[0]["value"][1])
            and float(current[0]["value"][1]) <= normal_ceiling
            and ALERTS[mode] not in current_alerts(prometheus_url)
        ):
            return stamp(utc_now())
        time.sleep(10)
    raise RuntimeError("FAIL: alert or metric did not recover within 15 minutes")


def wait_documents_ready(api_url: str, document_ids: list[int]) -> str:
    """The queue metric can clear before the final in-progress job finishes."""
    deadline = time.monotonic() + 5 * 60
    expected = set(document_ids)
    while time.monotonic() < deadline:
        status, documents = json_request(api_url + "/documents")
        if status != 200 or not isinstance(documents, list):
            raise RuntimeError("Could not inspect fixture document recovery")
        states = {document["id"]: document["status"] for document in documents if document.get("id") in expected}
        if len(states) == len(expected) and all(state == "ready" for state in states.values()):
            return stamp(utc_now())
        if any(state == "failed" for state in states.values()):
            raise RuntimeError("FAIL: a fixture document failed during backlog recovery")
        time.sleep(10)
    raise RuntimeError("FAIL: a fixture document remained pending after queue recovery")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("baseline", "latency", "backlog", "errors", "off"))
    parser.add_argument("--api-url", default="http://127.0.0.1:18000")
    parser.add_argument("--prometheus-url", default="http://127.0.0.1:19090")
    parser.add_argument("--alertmanager-url", default="http://127.0.0.1:19093")
    parser.add_argument("--execute", action="store_true", help="Confirm approved kind mutation/traffic")
    args = parser.parse_args()
    if not args.execute:
        parser.error("--execute is required after separate kind/traffic approval")
    api_url = local_url(args.api_url)
    prometheus_url = local_url(args.prometheus_url)
    alertmanager_url = local_url(args.alertmanager_url)
    if args.mode == "off":
        set_fault("off", 0)
        print(json.dumps({"mode": "off", "at": stamp(utc_now())}))
        return 0
    ensure_ready_document(api_url)
    if args.mode == "baseline":
        # 70 minutes provides more than the 65-minute rule history requirement.
        started = utc_now()
        output = chat_traffic(api_url, prometheus_url, 70 * 60, "baseline")
        if output["responses"].get("200", 0) < 65:
            raise RuntimeError("Baseline traffic did not produce enough successful fixture chats")
        print(json.dumps({"mode": "baseline", "started_at": stamp(started), "ended_at": stamp(utc_now()), **output}))
        return 0
    preflight(prometheus_url)
    ensure_no_active_silences(alertmanager_url)
    # Keep ARQ jobs waiting on the serial gate below the worker's 5-minute timeout.
    # Thirty seconds keeps at least three queued jobs above the learned band
    # throughout the five-minute alert hold, while every job remains below
    # ARQ's five-minute execution timeout.
    delay = {"latency": 3, "backlog": 30, "errors": 0}[args.mode]
    started = utc_now()
    result: dict = {}
    try:
        set_fault(args.mode, delay, started + timedelta(minutes=13))
        # Projected ConfigMap refresh is eventual; wait before fixture traffic.
        time.sleep(90)
        if args.mode == "backlog":
            result = backlog_traffic(api_url, prometheus_url, 8 * 60)
        else:
            result = chat_traffic(api_url, prometheus_url, 10 * 60, args.mode)
    finally:
        set_fault("off", 0)
    result.update(mode=args.mode, started_at=stamp(started), fault_disabled_at=stamp(utc_now()))
    recovery_error = None
    if "firing" in result.get("alert_transitions", {}):
        try:
            result["resolved_at"] = wait_recovery(api_url, prometheus_url, args.mode)
            if args.mode == "backlog":
                result["documents_ready_at"] = wait_documents_ready(
                    api_url, result["accepted_document_ids"],
                )
        except RuntimeError as exc:
            recovery_error = str(exc)
            result["recovery_error"] = recovery_error
    print(json.dumps(result, sort_keys=True))
    if args.mode == "latency" and result.get("responses", {}).get("200", 0) < 30:
        raise RuntimeError("FAIL: latency traffic did not preserve successful chat responses")
    if args.mode == "errors" and result.get("responses", {}).get("502", 0) < 30:
        raise RuntimeError("FAIL: error traffic did not produce the existing 502 contract")
    if "firing" not in result.get("alert_transitions", {}):
        raise RuntimeError("FAIL: target anomaly alert never reached firing")
    if recovery_error is not None:
        raise RuntimeError(recovery_error)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (RuntimeError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)
