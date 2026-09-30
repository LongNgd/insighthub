"""Standalone Day 5 verifier contracts with fresh sanitized audit observations."""

import asyncio
import hashlib
import hmac
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

import pytest
from fastapi import HTTPException
from starlette.requests import Request


REPO_ROOT = Path(os.environ.get("INSIGHTHUB_REPO_ROOT", Path(__file__).resolve().parents[3]))
BOT_ROOT = REPO_ROOT / "chatops-bot"
if str(BOT_ROOT) not in sys.path:
    sys.path.insert(0, str(BOT_ROOT))

from app import main, queue  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.errors import PolicyDenied  # noqa: E402
from app.events import NormalizedSlackEvent  # noqa: E402
from app.policy import (  # noqa: E402
    DEFAULT_CATALOG,
    ActionDefinition,
    ActionTier,
    _approval_key,
    _request_key,
    approve_request,
    create_scale_request,
    execute_approved_request,
)


class MemoryRedis:
    """Minimal Redis semantic double for policy and queue verifier contracts."""

    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.jobs: list[tuple[str, dict[str, str], str]] = []

    async def set(
        self,
        key: str,
        value: str,
        *,
        nx: bool = False,
        xx: bool = False,
        ex: int | None = None,
    ) -> bool:
        _ = ex
        if nx and key in self.values:
            return False
        if xx and key not in self.values:
            return False
        self.values[key] = value
        return True

    async def get(self, key: str) -> str | None:
        return self.values.get(key)

    async def enqueue_job(
        self, function: str, payload: dict[str, str], *, _queue_name: str
    ) -> object:
        self.jobs.append((function, payload, _queue_name))
        return object()

    async def eval(self, script: str, count: int, *args: object) -> str | int:
        keys = [str(value) for value in args[:count]]
        values = [str(value) for value in args[count:]]
        if "request.state = 'approved'" in script:
            request = self._record(keys[0])
            if request is None or request.get("state") != "approval_required":
                return "invalid_state"
            request["state"] = "approved"
            request["approver_user_id"] = values[0]
            encoded = json.dumps(request, sort_keys=True, separators=(",", ":"))
            self.values[keys[0]] = encoded
            self.values[keys[1]] = encoded
            return "approved"
        if "approval.binding_hash" in script:
            approval = self._record(keys[0])
            if approval is None:
                return "missing"
            binding, requester, action, target, replicas, request_id, requested_at = values
            matches = (
                approval.get("state") == "approved"
                and approval.get("binding_hash") == binding
                and approval.get("requester_user_id") == requester
                and approval.get("action") == action
                and approval.get("target") == target
                and approval.get("arguments") == {"replicas": int(replicas)}
                and approval.get("request_id") == request_id
                and approval.get("requested_at") == requested_at
            )
            if not matches:
                return "mismatch"
            del self.values[keys[0]]
            return "consumed"
        return 0

    def _record(self, key: str) -> dict[str, object] | None:
        value = self.values.get(key)
        return json.loads(value) if value is not None else None


class NoopExecutor:
    """Proves that a denied request does not reach an executor."""

    def __init__(self) -> None:
        self.calls = 0

    async def execute(self, request: object) -> None:
        _ = request
        self.calls += 1


@pytest.fixture(autouse=True)
def configured_day5(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SLACK_SIGNING_SECRET", "milestone-signing-secret")
    monkeypatch.setenv("SLACK_BOT_USER_ID", "UBOT")
    monkeypatch.setenv("CHATOPS_REDIS_URL", "redis://milestone.invalid:6379/0")
    monkeypatch.setenv("CHATOPS_KUBERNETES_NAMESPACE", "insighthub-prod")
    monkeypatch.setenv("CHATOPS_SCALE_DEPLOYMENT_ALLOWLIST", "api")
    monkeypatch.setenv("CHATOPS_APPROVER_USER_IDS", "UAPPROVER")
    monkeypatch.setenv("CHATOPS_CONFIRMATION_HMAC_KEY", "milestone-confirmation-key")
    monkeypatch.setenv("CHATOPS_AUDIT_SINK", "stdout")
    monkeypatch.delenv("CHATOPS_AUDIT_FILE", raising=False)
    get_settings.cache_clear()
    queue._pool = None
    yield
    queue._pool = None
    get_settings.cache_clear()


def run(coroutine: Any) -> Any:
    return asyncio.run(coroutine)


def scale_event() -> NormalizedSlackEvent:
    return NormalizedSlackEvent(
        event_id="Evmilestone",
        run_id="00000000-0000-4000-8000-000000000005",
        team_id="Tmilestone",
        user_id="UREQUESTER",
        channel_id="Cmilestone",
        thread_ts="123.456",
        event_type="app_mention",
        text="scale api to 3",
    )


def slack_request(body: bytes, headers: dict[str, str]) -> Request:
    scope: dict[str, object] = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": "/slack/events",
        "raw_path": b"/slack/events",
        "query_string": b"",
        "headers": [(name.encode("ascii"), value.encode("ascii")) for name, value in headers.items()],
        "client": ("testclient", 50000),
        "server": ("testserver", 80),
    }
    sent = False

    async def receive() -> dict[str, object]:
        nonlocal sent
        if sent:
            return {"type": "http.disconnect"}
        sent = True
        return {"type": "http.request", "body": body, "more_body": False}

    return Request(scope, receive)


def test_invalid_signature() -> None:
    body = b'{"type":"event_callback"}'
    timestamp = str(int(time.time()))
    wrong_signature = "v0=" + hmac.new(
        b"different-secret",
        b"v0:" + timestamp.encode("ascii") + b":" + body,
        hashlib.sha256,
    ).hexdigest()

    with pytest.raises(HTTPException) as raised:
        run(
            main.slack_events(
                slack_request(
                    body,
                    {
                        "x-slack-request-timestamp": timestamp,
                        "x-slack-signature": wrong_signature,
                    },
                )
            )
        )

    assert raised.value.status_code == 401
    assert raised.value.detail == "Unauthorized Slack request."


def test_permission_denied() -> None:
    redis = MemoryRedis()
    pending = run(create_scale_request(redis, scale_event()))
    assert pending is not None
    executor = NoopExecutor()

    with pytest.raises(PolicyDenied):
        run(execute_approved_request(redis, pending.request_id, executor))

    assert executor.calls == 0


def test_approval_required() -> None:
    pending = run(create_scale_request(MemoryRedis(), scale_event()))

    assert pending is not None
    assert pending.action == "scale_deployment"
    assert pending.target == "insighthub-prod/api"


def test_approval_bound_to_action() -> None:
    redis = MemoryRedis()
    pending = run(create_scale_request(redis, scale_event()))
    assert pending is not None
    run(approve_request(redis, pending.request_id, "UAPPROVER"))

    stored = redis._record(_request_key(pending.request_id))
    assert stored is not None
    stored["action"] = "scale_deployment_other"
    redis.values[_request_key(pending.request_id)] = json.dumps(
        stored, sort_keys=True, separators=(",", ":")
    )
    catalog = {
        "scale_deployment_other": ActionDefinition(
            "scale_deployment_other", ActionTier.WRITE
        )
    }

    with pytest.raises(PolicyDenied):
        run(execute_approved_request(redis, pending.request_id, NoopExecutor(), catalog=catalog))

    approval = redis._record(_approval_key(pending.request_id))
    assert approval is not None
    assert approval["action"] == "scale_deployment"


def test_duplicate_event() -> None:
    redis = MemoryRedis()
    queue._pool = redis  # type: ignore[assignment]

    first = run(queue.enqueue_authenticated_event(scale_event()))
    second = run(queue.enqueue_authenticated_event(scale_event()))

    assert first.accepted is True
    assert second.accepted is False
    assert len(redis.jobs) == 1
    assert redis.jobs[0][0] == queue.PROCESS_EVENT_JOB
