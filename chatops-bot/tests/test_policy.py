"""Permission enforcement tests for server-side ChatOps mutations."""

import asyncio
import json
import logging
import time
from pathlib import Path
from typing import Any

import pytest

from app.config import get_settings
from app.errors import MutationOutcomeUnknown, PolicyDenied
from app.events import NormalizedSlackEvent
from app.policy import (
    DEFAULT_CATALOG,
    ActionDefinition,
    ActionRequest,
    ActionTier,
    ConfirmationToken,
    _approval_key,
    _confirmation_key,
    _request_key,
    _reconciliation_key,
    approve_request,
    create_scale_request,
    execute_approved_request,
    issue_confirmation,
)


class PolicyRedis:
    """A small Redis/Lua semantic double; production always uses Redis itself."""

    def __init__(self) -> None:
        self.values: dict[str, str] = {}

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

    async def eval(self, script: str, count: int, *args: object) -> str:
        keys = [str(value) for value in args[:count]]
        values = [str(value) for value in args[count:]]
        now = int(time.time())
        if "request.state = 'approved'" in script:
            request = self._json(keys[0])
            if request is None:
                return "missing"
            if int(request["expires_at"]) <= now:
                return "expired"
            if keys[1] in self.values:
                return "replayed"
            if request.get("state") != "approval_required":
                return "invalid_state"
            request["state"] = "approved"
            request["approver_user_id"] = values[0]
            request["approval_issued_at"] = now
            encoded = json.dumps(request, sort_keys=True, separators=(",", ":"))
            self.values[keys[0]] = encoded
            self.values[keys[1]] = encoded
            return "approved"
        approval = self._json(keys[0])
        if approval is None:
            return "missing"
        if "confirmation_raw" in script:
            confirmation = self._json(keys[1])
            if confirmation is None:
                return "missing"
            if int(approval["expires_at"]) <= now or int(confirmation["expires_at"]) <= now:
                return "expired"
            binding, requester, action, target, replicas, request_id, requested_at, token_mac = values
            if not self._matches(
                approval, binding, requester, action, target, replicas, request_id, requested_at
            ):
                return "approval_mismatch"
            if confirmation.get("binding_hash") != binding or confirmation.get("token_mac") != token_mac:
                return "confirmation_mismatch"
            del self.values[keys[0]]
            del self.values[keys[1]]
            return "consumed"
        if int(approval["expires_at"]) <= now:
            del self.values[keys[0]]
            return "expired"
        binding, requester, action, target, replicas, request_id, requested_at = values
        if not self._matches(
            approval, binding, requester, action, target, replicas, request_id, requested_at
        ):
            return "mismatch"
        del self.values[keys[0]]
        return "consumed"

    def _json(self, key: str) -> dict[str, object] | None:
        value = self.values.get(key)
        return json.loads(value) if value is not None else None

    @staticmethod
    def _matches(
        record: dict[str, object],
        binding: str,
        requester: str,
        action: str,
        target: str,
        replicas: str,
        request_id: str,
        requested_at: str,
    ) -> bool:
        return (
            record.get("state") == "approved"
            and record.get("binding_hash") == binding
            and record.get("requester_user_id") == requester
            and record.get("action") == action
            and record.get("target") == target
            and record.get("request_id") == request_id
            and record.get("requested_at") == requested_at
            and record.get("arguments") == {"replicas": int(replicas)}
        )


class CountingExecutor:
    def __init__(self, unknown: bool = False) -> None:
        self.calls = 0
        self.unknown = unknown

    async def execute(self, request: ActionRequest) -> None:
        _ = request
        self.calls += 1
        if self.unknown:
            raise MutationOutcomeUnknown()


@pytest.fixture(autouse=True)
def policy_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CHATOPS_KUBERNETES_NAMESPACE", "insighthub-prod")
    monkeypatch.setenv("CHATOPS_SCALE_DEPLOYMENT_ALLOWLIST", "api,worker")
    monkeypatch.setenv("CHATOPS_APPROVER_USER_IDS", "UAPPROVER,USECOND")
    monkeypatch.setenv("CHATOPS_CONFIRMATION_HMAC_KEY", "test-confirmation-hmac")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def run(coroutine: Any) -> Any:
    return asyncio.run(coroutine)


def scale_event(text: str = "scale api to 3", user: str = "U_REQUESTER") -> NormalizedSlackEvent:
    return NormalizedSlackEvent(
        event_id="Ev-policy",
        team_id="T-policy",
        user_id=user,
        channel_id="C-policy",
        thread_ts="123.456",
        event_type="app_mention",
        text=text,
    )


def request(redis: PolicyRedis) -> ActionRequest:
    result = run(create_scale_request(redis, scale_event()))
    assert result is not None
    return result


def approve(redis: PolicyRedis, request_value: ActionRequest) -> None:
    run(approve_request(redis, request_value.request_id, "UAPPROVER"))


def test_only_fixed_allowlisted_scale_command_creates_a_write_request() -> None:
    redis = PolicyRedis()
    first = request(redis)
    assert first.target == "insighthub-prod/api"
    second = run(create_scale_request(redis, scale_event()))
    assert second is not None
    assert second.request_id == first.request_id
    assert run(create_scale_request(redis, scale_event("scale api to 21"))) is None
    assert run(create_scale_request(redis, scale_event("scale other to 3"))) is None
    assert run(create_scale_request(redis, scale_event("scale api to 3 namespace=kube-system"))) is None


def test_write_requires_approval_and_executor_runs_only_after_atomic_consume() -> None:
    redis = PolicyRedis()
    pending = request(redis)
    executor = CountingExecutor()

    with pytest.raises(PolicyDenied):
        run(execute_approved_request(redis, pending.request_id, executor))
    assert executor.calls == 0

    approve(redis, pending)
    assert run(execute_approved_request(redis, pending.request_id, executor)).state == "executed"
    assert executor.calls == 1


def test_self_or_unallowlisted_approver_is_denied() -> None:
    redis = PolicyRedis()
    pending = request(redis)
    with pytest.raises(PolicyDenied):
        run(approve_request(redis, pending.request_id, "U_REQUESTER"))
    with pytest.raises(PolicyDenied):
        run(approve_request(redis, pending.request_id, "U_INTRUDER"))


def test_approval_replay_is_denied_before_any_executor_call() -> None:
    redis = PolicyRedis()
    pending = request(redis)
    approve(redis, pending)
    with pytest.raises(PolicyDenied):
        run(approve_request(redis, pending.request_id, "USECOND"))


@pytest.mark.parametrize(
    "field,value",
    [
        ("requester_user_id", "U_OTHER"),
        ("action", "other_action"),
        ("target", "insighthub-prod/worker"),
        ("arguments", {"replicas": 4}),
        ("request_id", "different-request-id-1234"),
        ("requested_at", "2020-01-01T00:00:00+00:00"),
        ("expires_at", 0),
    ],
)
def test_approval_binding_rejects_each_modified_field(field: str, value: object) -> None:
    redis = PolicyRedis()
    pending = request(redis)
    approve(redis, pending)
    key = _approval_key(pending.request_id)
    record = json.loads(redis.values[key])
    record[field] = value
    redis.values[key] = json.dumps(record, sort_keys=True, separators=(",", ":"))
    executor = CountingExecutor()

    with pytest.raises(PolicyDenied):
        run(execute_approved_request(redis, pending.request_id, executor))
    assert executor.calls == 0


def test_replay_and_concurrent_consumers_reach_executor_once() -> None:
    redis = PolicyRedis()
    pending = request(redis)
    approve(redis, pending)
    executor = CountingExecutor()

    async def execute_twice() -> list[object]:
        return await asyncio.gather(
            execute_approved_request(redis, pending.request_id, executor),
            execute_approved_request(redis, pending.request_id, executor),
            return_exceptions=True,
        )

    results = run(execute_twice())
    assert executor.calls == 1
    assert sum(isinstance(item, PolicyDenied) for item in results) == 1
    with pytest.raises(PolicyDenied):
        run(execute_approved_request(redis, pending.request_id, executor))


def test_destructive_framework_requires_bound_one_time_confirmation() -> None:
    redis = PolicyRedis()
    pending = ActionRequest(
        request_id="destructive-request-id-1234",
        event_id="event-opaque",
        requester_user_id="U_REQUESTER",
        action="future_destructive",
        target="insighthub-prod/api",
        arguments={"replicas": 1},
        requested_at="2026-09-29T00:00:00+00:00",
        expires_at=int(time.time()) + 300,
    )
    redis.values[_request_key(pending.request_id)] = json.dumps(pending.to_record())
    catalog = {
        pending.action: ActionDefinition(pending.action, ActionTier.DESTRUCTIVE),
    }
    approve(redis, pending)
    executor = CountingExecutor()

    with pytest.raises(PolicyDenied):
        run(execute_approved_request(redis, pending.request_id, executor, catalog=catalog))
    token = run(issue_confirmation(redis, pending, catalog=catalog))
    with pytest.raises(PolicyDenied):
        run(
            execute_approved_request(
                redis,
                pending.request_id,
                executor,
                catalog=catalog,
                confirmation=ConfirmationToken(token.confirmation_id, "wrong-token"),
            )
        )
    assert executor.calls == 0
    assert run(
        execute_approved_request(
            redis,
            pending.request_id,
            executor,
            catalog=catalog,
            confirmation=token,
        )
    ).state == "executed"
    with pytest.raises(PolicyDenied):
        run(
            execute_approved_request(
                redis, pending.request_id, executor, catalog=catalog, confirmation=token
            )
        )


def test_expired_destructive_confirmation_is_denied() -> None:
    redis = PolicyRedis()
    pending = ActionRequest(
        request_id="expired-confirmation-id-1234",
        event_id="event-opaque",
        requester_user_id="U_REQUESTER",
        action="future_destructive",
        target="insighthub-prod/api",
        arguments={"replicas": 1},
        requested_at="2026-09-29T00:00:00+00:00",
        expires_at=int(time.time()) + 300,
    )
    redis.values[_request_key(pending.request_id)] = json.dumps(pending.to_record())
    catalog = {pending.action: ActionDefinition(pending.action, ActionTier.DESTRUCTIVE)}
    approve(redis, pending)
    token = run(issue_confirmation(redis, pending, catalog=catalog))
    key = _confirmation_key(token.confirmation_id)
    record = json.loads(redis.values[key])
    record["expires_at"] = 0
    redis.values[key] = json.dumps(record)

    with pytest.raises(PolicyDenied):
        run(
            execute_approved_request(
                redis,
                pending.request_id,
                CountingExecutor(),
                catalog=catalog,
                confirmation=token,
            )
        )


def test_unknown_mutation_outcome_is_recorded_without_retry() -> None:
    redis = PolicyRedis()
    pending = request(redis)
    approve(redis, pending)
    executor = CountingExecutor(unknown=True)

    result = run(execute_approved_request(redis, pending.request_id, executor))
    assert result.state == "reconciliation_required"
    assert executor.calls == 1
    assert _reconciliation_key(pending.request_id) in redis.values


def test_default_catalog_denies_unregistered_destructive_action() -> None:
    redis = PolicyRedis()
    pending = ActionRequest(
        request_id="unregistered-action-id-1234",
        event_id="event-opaque",
        requester_user_id="U_REQUESTER",
        action="future_destructive",
        target="insighthub-prod/api",
        arguments={"replicas": 1},
        requested_at="2026-09-29T00:00:00+00:00",
        expires_at=int(time.time()) + 300,
    )
    redis.values[_request_key(pending.request_id)] = json.dumps(pending.to_record())
    approve(redis, pending)
    with pytest.raises(PolicyDenied):
        run(execute_approved_request(redis, pending.request_id, CountingExecutor()))


def test_audit_does_not_leak_approval_or_confirmation_material(caplog: pytest.LogCaptureFixture) -> None:
    redis = PolicyRedis()
    caplog.set_level(logging.INFO, logger="chatops-bot.audit")
    pending = request(redis)
    approve(redis, pending)
    executor = CountingExecutor()
    run(execute_approved_request(redis, pending.request_id, executor))
    records = [json.loads(record.message) for record in caplog.records]
    assert {"approval_required", "allowed"} <= {record["decision"] for record in records}
    assert pending.request_id not in caplog.text
    assert "test-confirmation-hmac" not in caplog.text


def test_writer_rbac_is_namespaced_scale_only() -> None:
    manifest = Path(__file__).resolve().parents[2] / "kubernetes/chatops/chatops-scale-writer.yaml"
    content = manifest.read_text(encoding="utf-8")
    assert "kind: ServiceAccount" in content
    assert "resources: [\"deployments/scale\"]" in content
    assert "verbs: [\"patch\", \"update\"]" in content
    assert "kind: ClusterRole" not in content
    assert "delete" not in content
