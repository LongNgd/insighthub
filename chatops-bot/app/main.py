"""Fail-closed Slack HTTP event adapter for the Day 5 ChatOps bot."""

import json
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, PlainTextResponse, Response

from app.config import get_settings
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

    await prepare_authenticated_event(payload)
    return JSONResponse({"ok": True})


async def prepare_authenticated_event(payload: dict[str, Any]) -> None:
    """Integration seam for the later durable queue; it never invokes tools inline."""

    _ = payload


async def handle_question(question: str) -> str:
    # Day 5: transport -> deduplicated queue -> bounded read-only tool -> audit.
    # Mutation requires a separate identity and approval bound to exact action.
    raise NotImplementedError("Day 5 learner implementation")
