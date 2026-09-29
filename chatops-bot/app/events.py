"""Validated, normalized Slack event data for the durable queue."""

from dataclasses import asdict, dataclass
import hashlib
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

from app.errors import EventValidationError


@dataclass(frozen=True)
class NormalizedSlackEvent:
    """The minimal event shape needed by the worker; never log this object."""

    event_id: str
    run_id: str
    team_id: str
    user_id: str
    channel_id: str
    thread_ts: str
    event_type: str
    text: str

    @property
    def identity(self) -> str:
        """Return an opaque stable identity, safe for keys and audit fields."""

        source = f"{self.team_id}:{self.event_id}".encode("utf-8")
        return hashlib.sha256(source).hexdigest()

    @property
    def reply_client_message_id(self) -> str:
        """Return an opaque, stable UUID for Slack's duplicate-message handling."""

        return str(uuid5(NAMESPACE_URL, f"insighthub:reply:{self.identity}"))

    def to_job_payload(self) -> dict[str, str]:
        """Serialize only normalized fields for ARQ; raw Slack bodies stay out of logs."""

        return asdict(self)

    @classmethod
    def from_job_payload(cls, payload: dict[str, Any]) -> "NormalizedSlackEvent":
        """Re-validate ARQ data before it reaches the intent router."""

        if not isinstance(payload, dict):
            raise EventValidationError()
        try:
            fields = {name: payload[name] for name in cls.__dataclass_fields__}
        except KeyError as error:
            raise EventValidationError() from error
        if not all(isinstance(value, str) for value in fields.values()):
            raise EventValidationError()
        try:
            if str(UUID(fields["run_id"])) != fields["run_id"]:
                raise ValueError()
        except ValueError as error:
            raise EventValidationError() from error
        return cls(**fields)


def normalize_authenticated_event(payload: dict[str, Any]) -> NormalizedSlackEvent:
    """Extract a stable event identity after the HTTP transport authenticated it."""

    event = payload.get("event")
    event_id = payload.get("event_id")
    team_id = payload.get("team_id", "")
    if not isinstance(event, dict) or not isinstance(event_id, str) or not event_id.strip():
        raise EventValidationError()
    if not isinstance(team_id, str):
        raise EventValidationError()

    def required_event_string(name: str) -> str:
        value = event.get(name)
        if not isinstance(value, str) or not value.strip():
            raise EventValidationError()
        return value.strip()

    thread_ts = event.get("thread_ts", event.get("ts"))
    if not isinstance(thread_ts, str) or not thread_ts.strip():
        raise EventValidationError()
    text = event.get("text", "")
    if not isinstance(text, str):
        raise EventValidationError()
    return NormalizedSlackEvent(
        event_id=event_id.strip(),
        run_id=str(uuid4()),
        team_id=team_id.strip(),
        user_id=required_event_string("user"),
        channel_id=required_event_string("channel"),
        thread_ts=thread_ts.strip(),
        event_type=required_event_string("type"),
        text=text,
    )
