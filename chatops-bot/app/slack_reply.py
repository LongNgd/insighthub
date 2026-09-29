"""Bounded Slack reply adapter called only by the ARQ worker."""

import httpx

from app.config import get_settings
from app.errors import PermanentProcessingError, TransientProcessingError
from app.events import NormalizedSlackEvent


async def send_deferred_reply(
    event: NormalizedSlackEvent,
    reply_text: str,
    *,
    approval_request_id: str | None = None,
) -> None:
    """Post one deferred reply with a stable opaque client id across retries."""

    settings = get_settings()
    if not settings.slack_bot_token or not settings.slack_api_base_url:
        raise PermanentProcessingError()
    request_payload = {
        "channel": event.channel_id,
        "thread_ts": event.thread_ts,
        "text": reply_text,
        "client_msg_id": event.reply_client_message_id,
    }
    if approval_request_id is not None:
        # The only interactive value is an opaque server request ID. The handler
        # reloads requester, target and arguments from Redis after Slack auth.
        request_payload["blocks"] = [
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "Approve scale"},
                        "style": "primary",
                        "action_id": "chatops.approve_scale",
                        "value": approval_request_id,
                    }
                ],
            }
        ]
    try:
        async with httpx.AsyncClient(timeout=settings.slack_reply_timeout_seconds) as client:
            response = await client.post(
                f"{settings.slack_api_base_url}/chat.postMessage",
                headers={"Authorization": f"Bearer {settings.slack_bot_token}"},
                json=request_payload,
            )
    except httpx.TimeoutException as error:
        raise TransientProcessingError() from error
    except httpx.RequestError as error:
        raise TransientProcessingError() from error

    if response.status_code == 429 or response.status_code >= 500:
        raise TransientProcessingError()
    if response.status_code >= 400:
        raise PermanentProcessingError()
    try:
        response_payload = response.json()
    except ValueError as error:
        raise TransientProcessingError() from error
    if response_payload.get("ok") is True:
        return
    if response_payload.get("error") in {"ratelimited", "internal_error", "request_timeout"}:
        raise TransientProcessingError()
    raise PermanentProcessingError()
