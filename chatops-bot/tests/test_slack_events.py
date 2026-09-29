"""Security regression tests for the fail-closed Slack HTTP adapter."""

import asyncio
import hashlib
import hmac
import json
import logging
import time
from typing import Any

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from app import main
from app.audit import log_tool_call
from app.config import get_settings


SIGNING_SECRET = "test-signing-secret"
BOT_USER_ID = "U_BOT"


@pytest.fixture(autouse=True)
def configured_adapter(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SLACK_SIGNING_SECRET", SIGNING_SECRET)
    monkeypatch.setenv("SLACK_BOT_USER_ID", BOT_USER_ID)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def signed_headers(body: bytes, timestamp: int | None = None) -> dict[str, str]:
    request_timestamp = str(int(time.time()) if timestamp is None else timestamp)
    signature_base = b"v0:" + request_timestamp.encode("ascii") + b":" + body
    signature = "v0=" + hmac.new(
        SIGNING_SECRET.encode("utf-8"),
        signature_base,
        hashlib.sha256,
    ).hexdigest()
    return {
        "x-slack-request-timestamp": request_timestamp,
        "x-slack-signature": signature,
    }


def request_for(body: bytes, headers: dict[str, str]) -> Request:
    encoded_headers = [(name.encode("ascii"), value.encode("ascii")) for name, value in headers.items()]
    scope: dict[str, Any] = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": "/slack/events",
        "raw_path": b"/slack/events",
        "query_string": b"",
        "headers": encoded_headers,
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


def call_events(body: bytes, headers: dict[str, str]) -> object:
    return asyncio.run(main.slack_events(request_for(body, headers)))


def event_body(event: dict[str, object]) -> bytes:
    return json.dumps({"type": "event_callback", "event": event}, separators=(",", ":")).encode()


def test_valid_user_event_is_acknowledged_and_prepared(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: list[dict[str, Any]] = []

    async def capture(payload: dict[str, Any]) -> None:
        captured.append(payload)

    monkeypatch.setattr(main, "prepare_authenticated_event", capture)
    body = event_body({"type": "app_mention", "user": "U_USER", "text": "api healthy?"})

    response = call_events(body, signed_headers(body))

    assert response.body == b'{"ok":true}'
    assert captured == [json.loads(body)]


@pytest.mark.parametrize("headers", [{}, {"x-slack-request-timestamp": "123", "x-slack-signature": "v0=wrong"}])
def test_missing_or_invalid_signature_is_rejected_before_parse(headers: dict[str, str]) -> None:
    body = b"not-json-and-must-not-be-parsed"

    with pytest.raises(HTTPException) as raised:
        call_events(body, headers)

    assert raised.value.status_code == 401
    assert raised.value.detail == "Unauthorized Slack request."


@pytest.mark.parametrize(
    "timestamp",
    [int(time.time()) - 301, int(time.time()) + 301],
)
def test_expired_or_future_timestamp_is_rejected(timestamp: int) -> None:
    body = event_body({"type": "app_mention", "user": "U_USER"})

    with pytest.raises(HTTPException) as raised:
        call_events(body, signed_headers(body, timestamp))

    assert raised.value.status_code == 401


@pytest.mark.parametrize("timestamp", ["not-an-integer", "1.0", " 123"])
def test_malformed_timestamp_is_rejected(timestamp: str) -> None:
    body = event_body({"type": "app_mention", "user": "U_USER"})
    headers = signed_headers(body)
    headers["x-slack-request-timestamp"] = timestamp

    with pytest.raises(HTTPException) as raised:
        call_events(body, headers)

    assert raised.value.status_code == 401


def test_oversized_numeric_timestamp_is_rejected() -> None:
    body = event_body({"type": "app_mention", "user": "U_USER"})
    headers = signed_headers(body)
    headers["x-slack-request-timestamp"] = "9" * 5000

    with pytest.raises(HTTPException) as raised:
        call_events(body, headers)

    assert raised.value.status_code == 401


def test_url_challenge_is_echoed_only_after_authentication() -> None:
    challenge = "challenge-value"
    body = json.dumps({"type": "url_verification", "challenge": challenge}).encode()

    response = call_events(body, signed_headers(body))
    assert response.body == challenge.encode()

    with pytest.raises(HTTPException) as raised:
        call_events(body, {"x-slack-request-timestamp": str(int(time.time()))})

    assert raised.value.status_code == 401
    assert challenge not in raised.value.detail


@pytest.mark.parametrize(
    "event",
    [
        {"type": "app_mention", "bot_id": "B_BOT", "user": "U_OTHER"},
        {"type": "app_mention", "user": BOT_USER_ID},
    ],
)
def test_self_events_are_acknowledged_without_preparation(
    monkeypatch: pytest.MonkeyPatch,
    event: dict[str, object],
) -> None:
    async def fail_if_called(payload: dict[str, Any]) -> None:
        raise AssertionError("self-events must not reach the async integration seam")

    monkeypatch.setattr(main, "prepare_authenticated_event", fail_if_called)
    body = event_body(event)

    response = call_events(body, signed_headers(body))

    assert response.body == b'{"ok":true}'


def test_healthz_reflects_configured_adapter(monkeypatch: pytest.MonkeyPatch) -> None:
    assert main.health() == {"status": "ready", "ready": True, "transport": "slack_http"}

    monkeypatch.delenv("SLACK_SIGNING_SECRET")
    get_settings.cache_clear()

    assert main.health() == {"status": "not_ready", "ready": False, "transport": "slack_http"}


def test_logs_do_not_contain_slack_body_or_secret(caplog: pytest.LogCaptureFixture) -> None:
    raw_body = "do-not-log-slack-payload"
    caplog.set_level(logging.INFO, logger="chatops-bot.audit")

    log_tool_call(
        user="U_USER",
        tool="safe_tool",
        args={"payload": raw_body, "slack_signature": SIGNING_SECRET},
        result_summary=raw_body,
    )

    assert raw_body not in caplog.text
    assert SIGNING_SECRET not in caplog.text
