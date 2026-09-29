"""Configuration for the fail-closed Slack HTTP adapter."""

from dataclasses import dataclass
from functools import lru_cache
import os


@dataclass(frozen=True)
class Settings:
    """Environment-backed configuration without exposing secret values."""

    slack_signing_secret: str
    slack_bot_user_id: str
    redis_url: str
    queue_name: str
    queue_timeout_seconds: float
    worker_max_tries: int
    retry_base_seconds: float
    retry_max_seconds: float
    dedup_ttl_seconds: int
    reply_ttl_seconds: int
    intent_timeout_seconds: float
    mcp_timeout_seconds: float
    mcp_max_response_bytes: int
    kubernetes_namespace: str
    kubernetes_max_pods: int
    kubernetes_restart_threshold: int
    insighthub_mcp_url: str
    insighthub_mcp_bearer_token: str
    kubernetes_mcp_url: str
    kubernetes_mcp_bearer_token: str
    slack_reply_timeout_seconds: float
    slack_bot_token: str
    slack_api_base_url: str

    @property
    def slack_adapter_ready(self) -> bool:
        return bool(
            self.slack_signing_secret
            and self.slack_bot_user_id
            and self.redis_url
        )


@lru_cache
def get_settings() -> Settings:
    """Load Slack adapter configuration from the process environment."""

    return Settings(
        slack_signing_secret=os.getenv("SLACK_SIGNING_SECRET", "").strip(),
        slack_bot_user_id=os.getenv("SLACK_BOT_USER_ID", "").strip(),
        redis_url=os.getenv("CHATOPS_REDIS_URL", "").strip(),
        queue_name=os.getenv("CHATOPS_QUEUE_NAME", "chatops-events").strip(),
        queue_timeout_seconds=_bounded_float(
            "CHATOPS_QUEUE_TIMEOUT_SECONDS", 2, 0.1, 2.5
        ),
        worker_max_tries=_bounded_int("CHATOPS_WORKER_MAX_TRIES", 3, 1, 3),
        retry_base_seconds=_positive_float("CHATOPS_RETRY_BASE_SECONDS", 1),
        retry_max_seconds=_positive_float("CHATOPS_RETRY_MAX_SECONDS", 30),
        dedup_ttl_seconds=_bounded_int("CHATOPS_DEDUP_TTL_SECONDS", 86400, 60, 604800),
        reply_ttl_seconds=_bounded_int("CHATOPS_REPLY_TTL_SECONDS", 604800, 60, 604800),
        intent_timeout_seconds=_positive_float("CHATOPS_INTENT_TIMEOUT_SECONDS", 10),
        mcp_timeout_seconds=_bounded_float("CHATOPS_MCP_TIMEOUT_SECONDS", 5, 0.1, 10),
        mcp_max_response_bytes=_bounded_int(
            "CHATOPS_MCP_MAX_RESPONSE_BYTES", 65536, 1024, 262144
        ),
        kubernetes_namespace=_required_namespace("CHATOPS_KUBERNETES_NAMESPACE"),
        kubernetes_max_pods=_bounded_int("CHATOPS_KUBERNETES_MAX_PODS", 10, 1, 20),
        kubernetes_restart_threshold=_bounded_int(
            "CHATOPS_KUBERNETES_RESTART_THRESHOLD", 3, 1, 100
        ),
        insighthub_mcp_url=os.getenv("CHATOPS_INSIGHTHUB_MCP_URL", "").strip(),
        insighthub_mcp_bearer_token=os.getenv(
            "CHATOPS_INSIGHTHUB_MCP_BEARER_TOKEN", ""
        ).strip(),
        kubernetes_mcp_url=os.getenv("CHATOPS_KUBERNETES_MCP_URL", "").strip(),
        kubernetes_mcp_bearer_token=os.getenv(
            "CHATOPS_KUBERNETES_MCP_BEARER_TOKEN", ""
        ).strip(),
        slack_reply_timeout_seconds=_positive_float(
            "CHATOPS_SLACK_REPLY_TIMEOUT_SECONDS", 10
        ),
        slack_bot_token=os.getenv("SLACK_BOT_TOKEN", "").strip(),
        slack_api_base_url=os.getenv("SLACK_API_BASE_URL", "").strip().rstrip("/"),
    )


def _positive_float(name: str, default: float) -> float:
    """Read a finite positive timeout without surfacing malformed configuration."""

    value = os.getenv(name, str(default)).strip()
    try:
        parsed = float(value)
    except ValueError as error:
        raise ValueError(f"{name} must be a positive number") from error
    if parsed <= 0 or parsed == float("inf") or parsed != parsed:
        raise ValueError(f"{name} must be a finite positive number")
    return parsed


def _bounded_int(name: str, default: int, minimum: int, maximum: int) -> int:
    """Read an integer setting with a safe, documented bound."""

    value = os.getenv(name, str(default)).strip()
    try:
        parsed = int(value)
    except ValueError as error:
        raise ValueError(f"{name} must be an integer") from error
    if not minimum <= parsed <= maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}")
    return parsed


def _bounded_float(name: str, default: float, minimum: float, maximum: float) -> float:
    """Read a finite timeout that stays inside a documented safety bound."""

    parsed = _positive_float(name, default)
    if not minimum <= parsed <= maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}")
    return parsed


def _required_namespace(name: str) -> str:
    """Read the operator-owned namespace; Slack text must never select it."""

    value = os.getenv(name, "insighthub-prod").strip()
    if not value or len(value) > 63:
        raise ValueError(f"{name} must be a Kubernetes namespace")
    allowed = set("abcdefghijklmnopqrstuvwxyz0123456789-")
    if value[0] == "-" or value[-1] == "-" or any(char not in allowed for char in value):
        raise ValueError(f"{name} must be a Kubernetes namespace")
    return value
