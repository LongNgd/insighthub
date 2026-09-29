"""Fail-closed Slack HTTP event adapter for the Day 5 ChatOps bot."""

import asyncio
import json
from typing import Any
from urllib.parse import parse_qs

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, PlainTextResponse, Response

from app.config import get_settings
from app.errors import (
    EventValidationError,
    PolicyDenied,
    PolicyUnavailable,
    QueueUnavailable,
)
from app.events import normalize_authenticated_event
from app.policy import approve_request
from app.queue import enqueue_approved_action, enqueue_authenticated_event
from app.slack_auth import SlackAuthenticationError, verify_slack_request


app = FastAPI(title="InsightHub ChatOps skeleton", version="0.2.0")


@app.get("/healthz")
def health() -> dict[str, bool | str]:
    """Expose adapter readiness without returning configuration values."""

    settings = get_settings()
    return {
        "status": "ready" if settings.slack_adapter_ready else "not_ready",
        "ready": settings.slack_adapter_ready,
        "transport": "slack_http",
    }


@app.post("/slack/events")
async def slack_events(request: Request) -> Response:
    """Authenticate, validate and ACK Slack events without running tools inline."""

    settings = get_settings()
    if not settings.slack_adapter_ready:
        raise HTTPException(status_code=503, detail="Slack adapter is not configured.")

    raw_body = await request.body()
    try:
        verify_slack_request(
            raw_body=raw_body,
            signature=request.headers.get("x-slack-signature"),
            timestamp=request.headers.get("x-slack-request-timestamp"),
            signing_secret=settings.slack_signing_secret,
        )
    except SlackAuthenticationError as error:
        raise HTTPException(status_code=401, detail="Unauthorized Slack request.") from error

    try:
        payload = json.loads(raw_body)
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise HTTPException(status_code=400, detail="Invalid Slack event payload.") from error
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Invalid Slack event payload.")

    if payload.get("type") == "url_verification":
        challenge = payload.get("challenge")
        if not isinstance(challenge, str):
            raise HTTPException(status_code=400, detail="Invalid Slack event payload.")
        return PlainTextResponse(challenge)

    event = payload.get("event")
    if not isinstance(event, dict):
        raise HTTPException(status_code=400, detail="Invalid Slack event payload.")
    if "bot_id" in event or event.get("user") == settings.slack_bot_user_id:
        return JSONResponse({"ok": True})

    try:
        await asyncio.wait_for(
            prepare_authenticated_event(payload),
            timeout=settings.queue_timeout_seconds,
        )
    except EventValidationError as error:
        raise HTTPException(status_code=400, detail="Invalid Slack event payload.") from error
    except (QueueUnavailable, TimeoutError) as error:
        raise HTTPException(status_code=503, detail="Slack event queue is unavailable.") from error
    return JSONResponse({"ok": True})


async def prepare_authenticated_event(payload: dict[str, Any]) -> None:
    """Normalize and durably enqueue an authenticated event without processing it."""

    event = normalize_authenticated_event(payload)
    await enqueue_authenticated_event(event)


@app.post("/slack/interactions")
async def slack_interactions(request: Request) -> Response:
    """Accept only a signed, fixed approval button and reload all action data."""

    settings = get_settings()
    if not settings.slack_adapter_ready:
        raise HTTPException(status_code=503, detail="Slack adapter is not configured.")
    raw_body = await request.body()
    try:
        verify_slack_request(
            raw_body=raw_body,
            signature=request.headers.get("x-slack-signature"),
            timestamp=request.headers.get("x-slack-request-timestamp"),
            signing_secret=settings.slack_signing_secret,
        )
        payload = _parse_approval_interaction(raw_body)
    except (SlackAuthenticationError, ValueError) as error:
        raise HTTPException(status_code=401, detail="Unauthorized Slack request.") from error
    try:
        approved = await approve_request(
            await _queue_redis(), payload["request_id"], payload["approver_user_id"]
        )
        await enqueue_approved_action(approved.request_id)
    except PolicyDenied as error:
        raise HTTPException(status_code=403, detail="Approval was denied.") from error
    except (PolicyUnavailable, QueueUnavailable) as error:
        raise HTTPException(status_code=503, detail="Slack event queue is unavailable.") from error
    return JSONResponse({"ok": True})


async def _queue_redis() -> Any:
    """Use the durable queue Redis pool rather than a client-provided store."""

    from app.queue import initialize_queue

    return await initialize_queue()


def _parse_approval_interaction(raw_body: bytes) -> dict[str, str]:
    """Parse one Slack block action after authentication, never its action fields."""

    try:
        form = parse_qs(raw_body.decode("utf-8"), strict_parsing=True)
        payload_values = form.get("payload")
        if set(form) != {"payload"} or payload_values is None or len(payload_values) != 1:
            raise ValueError()
        payload = json.loads(payload_values[0])
    except (UnicodeDecodeError, ValueError, json.JSONDecodeError) as error:
        raise ValueError() from error
    if not isinstance(payload, dict) or payload.get("type") != "block_actions":
        raise ValueError()
    user = payload.get("user")
    actions = payload.get("actions")
    if not isinstance(user, dict) or not isinstance(user.get("id"), str):
        raise ValueError()
    if not isinstance(actions, list) or len(actions) != 1 or not isinstance(actions[0], dict):
        raise ValueError()
    action = actions[0]
    request_id = action.get("value")
    if action.get("action_id") != "chatops.approve_scale" or not isinstance(request_id, str):
        raise ValueError()
    return {"approver_user_id": user["id"], "request_id": request_id}
