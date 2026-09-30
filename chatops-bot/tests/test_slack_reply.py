"""Official Slack SDK adapter tests without an outbound Slack call."""

import asyncio
from typing import Any

import pytest
from slack_sdk.errors import SlackClientError

from app import slack_reply
from app.config import get_settings
from app.errors import PermanentProcessingError, TransientProcessingError
from app.events import NormalizedSlackEvent


def run(coroutine: Any) -> Any:
    return asyncio.run(coroutine)


def event() -> NormalizedSlackEvent:
    return NormalizedSlackEvent(
        event_id="Ev-reply",
        run_id="00000000-0000-4000-8000-000000000003",
        team_id="T-reply",
        user_id="U-reply",
        channel_id="C-reply",
        thread_ts="123.456",
        event_type="app_mention",
        text="health",
    )


class FakeClient:
    def __init__(self, response: object) -> None:
        self.response = response
        self.calls: list[dict[str, object]] = []

    async def chat_postMessage(self, **kwargs: object) -> object:
        self.calls.append(kwargs)
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


class FakeResponse(dict[str, object]):
    def __init__(self, *, status_code: int | None = None, **values: object) -> None:
        super().__init__(values)
        self.status_code = status_code


@pytest.fixture(autouse=True)
def configured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SLACK_BOT_TOKEN", "test-bot-token")
    monkeypatch.setenv("SLACK_API_BASE_URL", "https://slack.test/api")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_sdk_posts_stable_threaded_reply_without_exposing_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = FakeClient(FakeResponse(ok=True))
    captured_token: list[str] = []

    def create_client(settings: object) -> FakeClient:
        captured_token.append(getattr(settings, "slack_bot_token"))
        return fake

    monkeypatch.setattr(slack_reply, "_create_client", create_client)

    run(slack_reply.send_deferred_reply(event(), "safe reply"))

    assert captured_token == ["test-bot-token"]
    assert fake.calls == [
        {
            "channel": "C-reply",
            "thread_ts": "123.456",
            "text": "safe reply",
            "client_msg_id": event().reply_client_message_id,
        }
    ]


@pytest.mark.parametrize(
    "response",
    [
        FakeResponse(status_code=429, ok=False, error="ratelimited"),
        FakeResponse(status_code=503, ok=False, error="internal_error"),
        SlackClientError("provider detail must not escape"),
    ],
)
def test_sdk_transient_failures_are_retried_by_worker(
    monkeypatch: pytest.MonkeyPatch, response: object
) -> None:
    monkeypatch.setattr(slack_reply, "_create_client", lambda _: FakeClient(response))

    with pytest.raises(TransientProcessingError):
        run(slack_reply.send_deferred_reply(event(), "safe reply"))


def test_sdk_permanent_failure_is_not_retried(monkeypatch: pytest.MonkeyPatch) -> None:
    response = FakeResponse(status_code=401, ok=False, error="invalid_auth")
    monkeypatch.setattr(slack_reply, "_create_client", lambda _: FakeClient(response))

    with pytest.raises(PermanentProcessingError):
        run(slack_reply.send_deferred_reply(event(), "safe reply"))
