"""Unit coverage for the durable queue and deferred ChatOps worker."""

import asyncio
import json
import logging
from typing import Any

import pytest
from arq import Retry

from app import queue
from app.audit import log_audit_event
from app.config import get_settings
from app.errors import PermanentProcessingError, TransientProcessingError
from app.events import NormalizedSlackEvent


class FakeRedis:
    """Small async Redis double retaining state across adapter instances."""

    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.jobs: list[tuple[str, dict[str, str], str]] = []
        self.fail_enqueue = False

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
    ) -> object | None:
        if self.fail_enqueue:
            raise RuntimeError("redis unavailable")
        self.jobs.append((function, payload, _queue_name))
        return object()

    async def eval(self, script: str, count: int, key: str, *args: object) -> int | str:
        _ = script, count
        if len(args) == 1:
            value = str(args[0])
            if self.values.get(key) == value:
                del self.values[key]
                return 1
            return 0
        claim = str(args[0])
        current = self.values.get(key)
        if current == "sent":
            return "sent"
        if current is None:
            self.values[key] = claim
            return "claimed"
        if current == claim:
            return "claimed"
        return "in_progress"


@pytest.fixture(autouse=True)
def configured_pipeline(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SLACK_SIGNING_SECRET", "test-secret")
    monkeypatch.setenv("SLACK_BOT_USER_ID", "U_BOT")
    monkeypatch.setenv("CHATOPS_REDIS_URL", "redis://test.invalid:6379/0")
    monkeypatch.setenv("SLACK_BOT_TOKEN", "test-token")
    monkeypatch.setenv("SLACK_API_BASE_URL", "https://slack.test/api")
    monkeypatch.setenv("CHATOPS_RETRY_BASE_SECONDS", "2")
    monkeypatch.setenv("CHATOPS_RETRY_MAX_SECONDS", "10")
    get_settings.cache_clear()
    queue._pool = None
    yield
    queue._pool = None
    get_settings.cache_clear()


def sample_event() -> NormalizedSlackEvent:
    return NormalizedSlackEvent(
        event_id="Ev-1",
        run_id="00000000-0000-4000-8000-000000000001",
        team_id="T-1",
        user_id="U-1",
        channel_id="C-1",
        thread_ts="123.456",
        event_type="app_mention",
        text="health",
    )


def run(coroutine: Any) -> Any:
    return asyncio.run(coroutine)


def test_first_event_is_enqueued_once_and_duplicate_is_acknowledged() -> None:
    fake = FakeRedis()
    queue._pool = fake  # type: ignore[assignment]

    first = run(queue.enqueue_authenticated_event(sample_event()))
    second = run(queue.enqueue_authenticated_event(sample_event()))

    assert first.accepted is True
    assert second.accepted is False
    assert len(fake.jobs) == 1
    assert fake.jobs[0][0] == queue.PROCESS_EVENT_JOB


def test_concurrent_duplicate_claims_enqueue_only_one_job() -> None:
    fake = FakeRedis()
    queue._pool = fake  # type: ignore[assignment]

    async def enqueue_twice() -> list[queue.EnqueueResult]:
        return await asyncio.gather(
            queue.enqueue_authenticated_event(sample_event()),
            queue.enqueue_authenticated_event(sample_event()),
        )

    results = run(enqueue_twice())

    assert [result.accepted for result in results].count(True) == 1
    assert len(fake.jobs) == 1


def test_dedup_survives_a_new_queue_adapter_instance() -> None:
    fake = FakeRedis()
    queue._pool = fake  # type: ignore[assignment]
    assert run(queue.enqueue_authenticated_event(sample_event())).accepted

    queue._pool = fake  # type: ignore[assignment]
    assert not run(queue.enqueue_authenticated_event(sample_event())).accepted
    assert len(fake.jobs) == 1


def test_enqueue_failure_releases_only_its_claim_and_is_audited(
    caplog: pytest.LogCaptureFixture,
) -> None:
    fake = FakeRedis()
    fake.fail_enqueue = True
    queue._pool = fake  # type: ignore[assignment]
    caplog.set_level(logging.INFO, logger="chatops-bot.audit")

    with pytest.raises(Exception) as raised:
        run(queue.enqueue_authenticated_event(sample_event()))

    assert raised.value.__class__.__name__ == "QueueUnavailable"
    assert fake.values == {}
    record = json.loads(caplog.records[-1].message)
    assert record["action"] == "event_enqueue"
    assert record["decision"] == "denied"
    assert record["summary"] == "queue_unavailable"


def test_transient_processing_retries_with_exponential_backoff(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app import worker

    async def transient(event: NormalizedSlackEvent) -> Any:
        _ = event
        raise TransientProcessingError()

    monkeypatch.setattr(worker, "route_authenticated_event", transient)
    with pytest.raises(Retry) as raised:
        run(worker.process_slack_event_job({"job_try": 2, "redis": FakeRedis()}, sample_event().to_job_payload()))

    assert raised.value.defer_score == 4000


def test_permanent_processing_error_does_not_retry(monkeypatch: pytest.MonkeyPatch) -> None:
    from app import worker

    async def permanent(event: NormalizedSlackEvent) -> Any:
        _ = event
        raise PermanentProcessingError()

    monkeypatch.setattr(worker, "route_authenticated_event", permanent)
    with pytest.raises(PermanentProcessingError):
        run(worker.process_slack_event_job({"job_try": 1, "redis": FakeRedis()}, sample_event().to_job_payload()))


def test_transient_failure_is_exhausted_after_three_attempts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app import worker

    async def transient(event: NormalizedSlackEvent) -> Any:
        _ = event
        raise TransientProcessingError()

    monkeypatch.setattr(worker, "route_authenticated_event", transient)
    with pytest.raises(TransientProcessingError):
        run(worker.process_slack_event_job({"job_try": 3, "redis": FakeRedis()}, sample_event().to_job_payload()))


def test_reply_is_not_sent_again_when_a_completed_job_is_retried(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app import worker
    from app.intents import IntentResult

    sent: list[str] = []
    redis = FakeRedis()

    async def route(event: NormalizedSlackEvent) -> IntentResult:
        _ = event
        return IntentResult(action="insighthub_health", reply_text="safe reply")

    async def reply(event: NormalizedSlackEvent, text: str) -> None:
        sent.append(f"{event.reply_client_message_id}:{text}")

    monkeypatch.setattr(worker, "route_authenticated_event", route)
    monkeypatch.setattr(worker, "send_deferred_reply", reply)
    payload = sample_event().to_job_payload()
    run(worker.process_slack_event_job({"job_try": 1, "redis": redis}, payload))
    run(worker.process_slack_event_job({"job_try": 2, "redis": redis}, payload))

    assert sent == [f"{sample_event().reply_client_message_id}:safe reply"]


def test_concurrent_reply_claim_allows_only_one_sender(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app import worker
    from app.intents import IntentResult

    sent: list[str] = []
    redis = FakeRedis()

    async def route(event: NormalizedSlackEvent) -> IntentResult:
        _ = event
        return IntentResult(action="insighthub_health", reply_text="safe reply")

    async def reply(event: NormalizedSlackEvent, text: str) -> None:
        _ = event, text
        await asyncio.sleep(0)
        sent.append("sent")

    monkeypatch.setattr(worker, "route_authenticated_event", route)
    monkeypatch.setattr(worker, "send_deferred_reply", reply)

    async def process_twice() -> list[object]:
        return await asyncio.gather(
            worker.process_slack_event_job(
                {"job_try": 1, "job_id": "job-one", "redis": redis},
                sample_event().to_job_payload(),
            ),
            worker.process_slack_event_job(
                {"job_try": 1, "job_id": "job-two", "redis": redis},
                sample_event().to_job_payload(),
            ),
            return_exceptions=True,
        )

    results = run(process_twice())

    assert sent == ["sent"]
    assert any(isinstance(result, Retry) for result in results)


def test_audit_contains_required_sanitized_fields(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO, logger="chatops-bot.audit")
    log_audit_event(
        event_id=sample_event().identity,
        run_id=sample_event().run_id,
        user="U-1",
        action="event_enqueue",
        tool="queue",
        decision="allowed",
        approval_state="not_required",
        summary="queued",
    )

    record = json.loads(caplog.records[-1].message)
    assert {"timestamp", "event_id", "run_id", "user", "action", "tool", "decision", "approval", "summary"} <= set(record)
    assert record["event_id"] == sample_event().identity
    assert "test-token" not in caplog.text
