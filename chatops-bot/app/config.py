"""Configuration for the fail-closed Slack HTTP adapter."""

from dataclasses import dataclass
from functools import lru_cache
import os


@dataclass(frozen=True)
class Settings:
    """Environment-backed configuration without exposing secret values."""

    slack_signing_secret: str
    slack_bot_user_id: str

    @property
    def slack_adapter_ready(self) -> bool:
        return bool(self.slack_signing_secret and self.slack_bot_user_id)


@lru_cache
def get_settings() -> Settings:
    """Load Slack adapter configuration from the process environment."""

    return Settings(
        slack_signing_secret=os.getenv("SLACK_SIGNING_SECRET", "").strip(),
        slack_bot_user_id=os.getenv("SLACK_BOT_USER_ID", "").strip(),
    )
