"""Bounded, opt-in fault control for the local Day 4 fixture lab."""

import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from app.core.config import get_settings

MAX_CONTROL_BYTES = 1024
MAX_WINDOW = timedelta(minutes=15)


@dataclass(frozen=True)
class Day4Fault:
    mode: str
    delay_seconds: float
    expires_at: datetime


def active_fault(now: datetime | None = None) -> Day4Fault | None:
    """Fail closed for missing, stale or invalid control data; never log its content."""
    settings = get_settings()
    if not (
        settings.day4_chaos_enabled
        and settings.environment == "day4-kind"
        and settings.rag_mode == "fixture"
        and settings.day4_chaos_control_path
    ):
        return None
    try:
        with Path(settings.day4_chaos_control_path).open("rb") as stream:
            raw = stream.read(MAX_CONTROL_BYTES + 1)
        if len(raw) > MAX_CONTROL_BYTES:
            return None
        data = json.loads(raw)
        if not isinstance(data, dict) or set(data) != {"mode", "delay_seconds", "expires_at"}:
            return None
        mode = data["mode"]
        delay = data["delay_seconds"]
        if mode not in {"latency", "backlog", "errors"}:
            return None
        if isinstance(delay, bool) or not isinstance(delay, (int, float)):
            return None
        if mode == "errors" and delay != 0:
            return None
        if mode in {"latency", "backlog"} and not (1 <= delay <= 30):
            return None
        expires_at = datetime.fromisoformat(data["expires_at"].replace("Z", "+00:00"))
        current = now or datetime.now(UTC)
        if expires_at.tzinfo is None or not (current < expires_at <= current + MAX_WINDOW):
            return None
        return Day4Fault(mode, float(delay), expires_at)
    except (OSError, ValueError, TypeError, AttributeError, UnicodeError):
        return None
