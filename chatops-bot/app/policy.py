"""Server-side, Redis-backed permission enforcement for ChatOps actions."""

import hashlib
import hmac
import json
import re
import secrets
import time
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Protocol

from app.audit import log_audit_event
from app.config import Settings, get_settings
from app.errors import PolicyDenied, PolicyUnavailable
from app.events import NormalizedSlackEvent


class ActionTier(str, Enum):
    READ_ONLY = "read_only"
    WRITE = "write"
    DESTRUCTIVE = "destructive"


@dataclass(frozen=True)
class ActionDefinition:
    """A server-owned action; Slack text cannot create a definition."""

    action: str
    tier: ActionTier


@dataclass(frozen=True)
class ActionRequest:
    """The exact, canonical payload that authorization binds and executes."""

    request_id: str
    event_id: str
    requester_user_id: str
    action: str
    target: str
    arguments: dict[str, int]
    requested_at: str
    expires_at: int

    @property
    def binding_hash(self) -> str:
        payload = {
            "action": self.action,
            "arguments": self.arguments,
            "event_id": self.event_id,
            "request_id": self.request_id,
            "requested_at": self.requested_at,
            "requester_user_id": self.requester_user_id,
            "target": self.target,
            "version": 1,
        }
        encoded = json.dumps(
            payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True
        ).encode("utf-8")
        return hashlib.sha256(b"insighthub-chatops-policy-v1\0" + encoded).hexdigest()

    def to_record(self, state: str = "approval_required") -> dict[str, object]:
        return {
            "action": self.action,
            "arguments": self.arguments,
            "binding_hash": self.binding_hash,
            "event_id": self.event_id,
            "expires_at": self.expires_at,
            "request_id": self.request_id,
            "requested_at": self.requested_at,
            "requester_user_id": self.requester_user_id,
            "state": state,
            "target": self.target,
            "version": 1,
        }


@dataclass(frozen=True)
class ConfirmationToken:
    """Opaque one-time material; callers must never log either field."""

    confirmation_id: str
    token: str


@dataclass(frozen=True)
class ExecutionResult:
    """A sanitized terminal outcome used by the worker audit boundary."""

    state: str


class ActionExecutor(Protocol):
    """A narrow executor receives only an already-authorized catalog action."""

    async def execute(self, request: ActionRequest) -> None: ...


DEFAULT_CATALOG = {
    "scale_deployment": ActionDefinition("scale_deployment", ActionTier.WRITE),
}

_SCALE_COMMAND = re.compile(r"^scale ([a-z0-9](?:[-a-z0-9]{0,61}[a-z0-9])?) to ([0-9]{1,2})$")
_OPAQUE_ID = re.compile(r"^[A-Za-z0-9_-]{16,128}$")
_APPROVE_SCRIPT = """
local request_raw = redis.call('GET', KEYS[1])
if not request_raw then return 'missing' end
local request = cjson.decode(request_raw)
local now = tonumber(redis.call('TIME')[1])
if tonumber(request.expires_at) <= now then return 'expired' end
if redis.call('GET', KEYS[2]) then return 'replayed' end
if request.state ~= 'approval_required' then return 'invalid_state' end
request.state = 'approved'
request.approver_user_id = ARGV[1]
request.approval_issued_at = now
local ttl = tonumber(request.expires_at) - now
redis.call('SET', KEYS[1], cjson.encode(request), 'KEEPTTL')
redis.call('SET', KEYS[2], cjson.encode(request), 'EX', ttl)
return 'approved'
"""
_CONSUME_APPROVAL_SCRIPT = """
local approval_raw = redis.call('GET', KEYS[1])
if not approval_raw then return 'missing' end
local approval = cjson.decode(approval_raw)
local now = tonumber(redis.call('TIME')[1])
if tonumber(approval.expires_at) <= now then redis.call('DEL', KEYS[1]); return 'expired' end
if approval.binding_hash ~= ARGV[1] or approval.state ~= 'approved' or
  approval.requester_user_id ~= ARGV[2] or approval.action ~= ARGV[3] or
  approval.target ~= ARGV[4] or approval.request_id ~= ARGV[6] or
  approval.requested_at ~= ARGV[7] or approval.arguments.replicas ~= tonumber(ARGV[5])
then return 'mismatch' end
redis.call('DEL', KEYS[1])
return 'consumed'
"""
_CONSUME_DESTRUCTIVE_SCRIPT = """
local approval_raw = redis.call('GET', KEYS[1])
local confirmation_raw = redis.call('GET', KEYS[2])
if not approval_raw or not confirmation_raw then return 'missing' end
local approval = cjson.decode(approval_raw)
local confirmation = cjson.decode(confirmation_raw)
local now = tonumber(redis.call('TIME')[1])
if tonumber(approval.expires_at) <= now or tonumber(confirmation.expires_at) <= now then return 'expired' end
if approval.state ~= 'approved' or approval.binding_hash ~= ARGV[1] or
  approval.requester_user_id ~= ARGV[2] or approval.action ~= ARGV[3] or
  approval.target ~= ARGV[4] or approval.request_id ~= ARGV[6] or
  approval.requested_at ~= ARGV[7] or approval.arguments.replicas ~= tonumber(ARGV[5])
then return 'approval_mismatch' end
if confirmation.binding_hash ~= ARGV[1] or confirmation.token_mac ~= ARGV[8] then return 'confirmation_mismatch' end
redis.call('DEL', KEYS[1])
redis.call('DEL', KEYS[2])
return 'consumed'
"""


def parse_scale_command(text: str, settings: Settings | None = None) -> tuple[str, dict[str, int]] | None:
    """Parse one fixed command form; values cannot select a namespace or tool."""

    match = _SCALE_COMMAND.fullmatch(" ".join(text.casefold().split()))
    if match is None:
        return None
    deployment, replicas_text = match.groups()
    current = settings or get_settings()
    replicas = int(replicas_text)
    if deployment not in current.scale_deployment_allowlist or replicas > 20:
        return None
    return f"{current.kubernetes_namespace}/{deployment}", {"replicas": replicas}


async def create_scale_request(
    redis: Any, event: NormalizedSlackEvent, settings: Settings | None = None
) -> ActionRequest | None:
    """Persist an immutable, server-generated write request before replying."""

    current = settings or get_settings()
    parsed = parse_scale_command(event.text, current)
    if parsed is None:
        return None
    existing_id = await _load_event_request_id(redis, event.identity)
    if existing_id is not None:
        existing = await _load_request(redis, existing_id)
        if existing is not None:
            return existing
    target, arguments = parsed
    now = int(time.time())
    request = ActionRequest(
        request_id=secrets.token_urlsafe(24),
        event_id=event.identity,
        requester_user_id=event.user_id,
        action="scale_deployment",
        target=target,
        arguments=arguments,
        requested_at=datetime.now(timezone.utc).isoformat(),
        expires_at=now + current.approval_ttl_seconds,
    )
    try:
        created = await redis.set(
            _request_key(request.request_id),
            _encode(request.to_record()),
            nx=True,
            ex=current.approval_ttl_seconds,
        )
    except Exception as error:
        raise PolicyUnavailable() from error
    if not created:
        raise PolicyUnavailable()
    try:
        selected = await redis.set(
            _event_request_key(event.identity),
            request.request_id,
            nx=True,
            ex=current.approval_ttl_seconds,
        )
    except Exception as error:
        raise PolicyUnavailable() from error
    if not selected:
        existing_id = await _load_event_request_id(redis, event.identity)
        if existing_id is not None:
            existing = await _load_request(redis, existing_id)
            if existing is not None:
                return existing
        raise PolicyUnavailable()
    log_audit_event(
        event_id=request.event_id,
        user=request.requester_user_id,
        action=request.action,
        target=request.target,
        decision="approval_required",
        summary="write_approval_required",
        approval_state="approval_required",
        expires_at=request.expires_at,
        argument_keys=sorted(request.arguments),
    )
    return request


async def approve_request(
    redis: Any, request_id: str, approver_user_id: str, settings: Settings | None = None
) -> ActionRequest:
    """Allow a separately authenticated, configured approver exactly once."""

    current = settings or get_settings()
    request = await _load_request(redis, request_id)
    if request is None:
        _audit_denial(request_id, approver_user_id, "approval_missing")
        raise PolicyDenied()
    if (
        approver_user_id not in current.approver_user_ids
        or approver_user_id == request.requester_user_id
    ):
        _audit_request(request, approver_user_id, "denied", "approval_identity_denied")
        raise PolicyDenied()
    try:
        outcome = await redis.eval(
            _APPROVE_SCRIPT,
            2,
            _request_key(request_id),
            _approval_key(request_id),
            approver_user_id,
        )
    except Exception as error:
        raise PolicyUnavailable() from error
    if _decode_outcome(outcome) != "approved":
        _audit_request(request, approver_user_id, "denied", "approval_invalid")
        raise PolicyDenied()
    _audit_request(
        request,
        approver_user_id,
        "allowed",
        "approval_recorded",
        "approved",
    )
    return request


async def execute_approved_request(
    redis: Any,
    request_id: str,
    executor: ActionExecutor,
    *,
    confirmation: ConfirmationToken | None = None,
    catalog: Mapping[str, ActionDefinition] = DEFAULT_CATALOG,
) -> ExecutionResult:
    """Consume authorization atomically before a non-retriable side effect."""

    request = await _load_request(redis, request_id)
    if request is None:
        _audit_denial(request_id, "unknown", "request_missing")
        raise PolicyDenied()
    definition = catalog.get(request.action)
    if definition is None or definition.tier is ActionTier.READ_ONLY:
        _audit_request(request, None, "denied", "action_denied")
        raise PolicyDenied()
    approval = await _load_json(redis, _approval_key(request.request_id))
    approver = (
        approval.get("approver_user_id")
        if isinstance(approval, dict) and isinstance(approval.get("approver_user_id"), str)
        else None
    )
    if definition.tier is ActionTier.WRITE:
        await _consume_approval(redis, request)
    else:
        if confirmation is None:
            _audit_request(request, None, "denied", "confirmation_required")
            raise PolicyDenied()
        await _consume_destructive_confirmation(redis, request, confirmation)

    from app.errors import MutationOutcomeUnknown

    log_audit_event(
        event_id=request.event_id,
        user=request.requester_user_id,
        action=f"executor.{request.action}",
        target=request.target,
        approver_user_id=approver,
        decision="allowed",
        summary="dispatch",
        approval_state="consumed",
        argument_keys=sorted(request.arguments),
    )
    try:
        await executor.execute(request)
    except MutationOutcomeUnknown:
        await _record_reconciliation(redis, request)
        _audit_request(request, approver, "allowed", "reconciliation_required", "consumed")
        return ExecutionResult("reconciliation_required")
    except Exception:
        _audit_request(request, approver, "denied", "executor_failed", "consumed")
        raise
    _audit_request(request, approver, "allowed", "executed", "consumed")
    return ExecutionResult("executed")


async def issue_confirmation(
    redis: Any,
    request: ActionRequest,
    *,
    catalog: Mapping[str, ActionDefinition],
    settings: Settings | None = None,
) -> ConfirmationToken:
    """Provide a future destructive action with an opaque, Redis-backed token."""

    current = settings or get_settings()
    definition = catalog.get(request.action)
    if definition is None or definition.tier is not ActionTier.DESTRUCTIVE:
        raise PolicyDenied()
    if not current.confirmation_hmac_key:
        raise PolicyDenied()
    approval = await _load_json(redis, _approval_key(request.request_id))
    if approval is None or approval.get("binding_hash") != request.binding_hash:
        raise PolicyDenied()
    token = secrets.token_urlsafe(32)
    confirmation_id = secrets.token_urlsafe(24)
    expires_at = int(time.time()) + current.confirmation_ttl_seconds
    record = {
        "binding_hash": request.binding_hash,
        "expires_at": expires_at,
        "request_id": request.request_id,
        "token_mac": _token_mac(token, current.confirmation_hmac_key),
        "version": 1,
    }
    try:
        created = await redis.set(
            _confirmation_key(confirmation_id),
            _encode(record),
            nx=True,
            ex=current.confirmation_ttl_seconds,
        )
    except Exception as error:
        raise PolicyUnavailable() from error
    if not created:
        raise PolicyUnavailable()
    _audit_request(request, None, "allowed", "confirmation_issued", "approved")
    return ConfirmationToken(confirmation_id, token)


async def _consume_approval(redis: Any, request: ActionRequest) -> None:
    try:
        outcome = await redis.eval(
            _CONSUME_APPROVAL_SCRIPT,
            1,
            _approval_key(request.request_id),
            request.binding_hash,
            request.requester_user_id,
            request.action,
            request.target,
            str(request.arguments["replicas"]),
            request.request_id,
            request.requested_at,
        )
    except Exception as error:
        raise PolicyUnavailable() from error
    if _decode_outcome(outcome) != "consumed":
        _audit_request(request, None, "denied", "approval_invalid")
        raise PolicyDenied()


async def _consume_destructive_confirmation(
    redis: Any, request: ActionRequest, confirmation: ConfirmationToken
) -> None:
    if not _OPAQUE_ID.fullmatch(confirmation.confirmation_id):
        _audit_request(request, None, "denied", "confirmation_invalid")
        raise PolicyDenied()
    record = await _load_json(redis, _confirmation_key(confirmation.confirmation_id))
    current = get_settings()
    if (
        record is None
        or not current.confirmation_hmac_key
        or not isinstance(record.get("token_mac"), str)
        or not hmac.compare_digest(
            _token_mac(confirmation.token, current.confirmation_hmac_key),
            record["token_mac"],
        )
    ):
        _audit_request(request, None, "denied", "confirmation_invalid")
        raise PolicyDenied()
    try:
        outcome = await redis.eval(
            _CONSUME_DESTRUCTIVE_SCRIPT,
            2,
            _approval_key(request.request_id),
            _confirmation_key(confirmation.confirmation_id),
            request.binding_hash,
            request.requester_user_id,
            request.action,
            request.target,
            str(request.arguments["replicas"]),
            request.request_id,
            request.requested_at,
            record["token_mac"],
        )
    except Exception as error:
        raise PolicyUnavailable() from error
    if _decode_outcome(outcome) != "consumed":
        _audit_request(request, None, "denied", "confirmation_invalid")
        raise PolicyDenied()


async def _load_request(redis: Any, request_id: str) -> ActionRequest | None:
    if not _OPAQUE_ID.fullmatch(request_id):
        return None
    record = await _load_json(redis, _request_key(request_id))
    if record is None:
        return None
    try:
        request = ActionRequest(
            request_id=_required_string(record, "request_id"),
            event_id=_required_string(record, "event_id"),
            requester_user_id=_required_string(record, "requester_user_id"),
            action=_required_string(record, "action"),
            target=_required_string(record, "target"),
            arguments=_canonical_arguments(record.get("arguments")),
            requested_at=_required_string(record, "requested_at"),
            expires_at=_required_int(record, "expires_at"),
        )
    except (TypeError, ValueError):
        return None
    if (
        request.request_id != request_id
        or request.expires_at <= int(time.time())
        or record.get("binding_hash") != request.binding_hash
    ):
        return None
    return request


async def _load_json(redis: Any, key: str) -> dict[str, object] | None:
    try:
        raw = await redis.get(key)
    except Exception as error:
        raise PolicyUnavailable() from error
    if raw is None:
        return None
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8", errors="strict")
    if not isinstance(raw, str):
        return None
    try:
        value = json.loads(raw)
    except (TypeError, ValueError):
        return None
    return value if isinstance(value, dict) else None


async def _load_event_request_id(redis: Any, event_id: str) -> str | None:
    try:
        value = await redis.get(_event_request_key(event_id))
    except Exception as error:
        raise PolicyUnavailable() from error
    if isinstance(value, bytes):
        value = value.decode("utf-8", errors="replace")
    return value if isinstance(value, str) and _OPAQUE_ID.fullmatch(value) else None


async def _record_reconciliation(redis: Any, request: ActionRequest) -> None:
    record = {
        "action": request.action,
        "event_id": request.event_id,
        "request_id": request.request_id,
        "state": "reconciliation_required",
        "target": request.target,
    }
    try:
        await redis.set(
            _reconciliation_key(request.request_id), _encode(record), nx=True, ex=604800
        )
    except Exception as error:
        raise PolicyUnavailable() from error


def _request_key(request_id: str) -> str:
    return f"chatops:policy:request:{request_id}"


def _event_request_key(event_id: str) -> str:
    return f"chatops:policy:event:{event_id}"


def _approval_key(request_id: str) -> str:
    return f"chatops:policy:approval:{request_id}"


def _confirmation_key(confirmation_id: str) -> str:
    return f"chatops:policy:confirmation:{confirmation_id}"


def _reconciliation_key(request_id: str) -> str:
    return f"chatops:policy:reconciliation:{request_id}"


def _encode(value: Mapping[str, object]) -> str:
    return json.dumps(value, ensure_ascii=True, separators=(",", ":"), sort_keys=True)


def _decode_outcome(value: object) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value if isinstance(value, str) else "invalid"


def _token_mac(token: str, key: str) -> str:
    return hmac.new(key.encode("utf-8"), token.encode("utf-8"), hashlib.sha256).hexdigest()


def _canonical_arguments(value: object) -> dict[str, int]:
    if not isinstance(value, dict) or set(value) != {"replicas"}:
        raise ValueError()
    replicas = value["replicas"]
    if isinstance(replicas, bool) or not isinstance(replicas, int) or not 0 <= replicas <= 20:
        raise ValueError()
    return {"replicas": replicas}


def _required_string(value: Mapping[str, object], field: str) -> str:
    candidate = value.get(field)
    if not isinstance(candidate, str) or not candidate:
        raise ValueError()
    return candidate


def _required_int(value: Mapping[str, object], field: str) -> int:
    candidate = value.get(field)
    if isinstance(candidate, bool) or not isinstance(candidate, int):
        raise ValueError()
    return candidate


def _audit_request(
    request: ActionRequest,
    approver: str | None,
    decision: str,
    summary: str,
    approval_state: str | None = None,
) -> None:
    log_audit_event(
        event_id=request.event_id,
        user=request.requester_user_id,
        action=request.action,
        target=request.target,
        approver_user_id=approver,
        decision=decision,
        summary=summary,
        argument_keys=sorted(request.arguments),
        expires_at=request.expires_at,
        approval_state=approval_state,
    )


def _audit_denial(event_id: str, user: str, summary: str) -> None:
    log_audit_event(
        event_id=event_id,
        user=user,
        action="policy",
        decision="denied",
        summary=summary,
    )
