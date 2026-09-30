"""Bounded official Slack SDK reply adapter used only by the ARQ worker."""

from collections.abc import Mapping

import aiohttp
from slack_sdk.errors import SlackApiError, SlackClientError
from slack_sdk.web.async_client import AsyncWebClient

from app.config import Settings, get_settings
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
    request_payload: dict[str, object] = {
        "channel": event.channel_id,
        "thread_ts": event.thread_ts,
        "text": reply_text,
        "client_msg_id": event.reply_client_message_id,
    }
    if approval_request_id is not None:
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
        response = await _create_client(settings).chat_postMessage(**request_payload)
    except SlackApiError as error:
        _raise_classified_slack_error(
            status_code=error.response.status_code,
            error_code=_response_error_code(error.response.data),
        )
    except (SlackClientError, aiohttp.ClientError, TimeoutError) as error:
        raise TransientProcessingError() from error
    if response.get("ok") is True:
        return
    _raise_classified_slack_error(
        status_code=_response_status_code(response),
        error_code=_response_error_code(response),
    )


def _create_client(settings: Settings) -> AsyncWebClient:
    """Create a non-retrying SDK client; ARQ owns bounded retry semantics."""

    return AsyncWebClient(
        token=settings.slack_bot_token,
        base_url=f"{settings.slack_api_base_url}/",
        timeout=settings.slack_reply_timeout_seconds,
        retry_handlers=[],
    )


def _raise_classified_slack_error(*, status_code: int | None, error_code: str) -> None:
    """Classify safe status/code categories without surfacing provider details."""

    if status_code == 429 or (status_code is not None and status_code >= 500):
        raise TransientProcessingError()
    if error_code in {"ratelimited", "internal_error", "request_timeout"}:
        raise TransientProcessingError()
    raise PermanentProcessingError()


def _response_status_code(value: object) -> int | None:
    status_code = getattr(value, "status_code", None)
    return status_code if isinstance(status_code, int) else None


def _response_error_code(value: object) -> str:
    if not isinstance(value, Mapping):
        return ""
    error_code = value.get("error")
    return error_code if isinstance(error_code, str) else ""
