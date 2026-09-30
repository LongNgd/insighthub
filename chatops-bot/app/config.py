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
    insighthub_api_url: str
    prometheus_url: str
    kubernetes_kubeconfig: str
    slack_reply_timeout_seconds: float
    slack_bot_token: str
    slack_api_base_url: str
    approver_user_ids: frozenset[str]
    scale_deployment_allowlist: frozenset[str]
    approval_ttl_seconds: int
    confirmation_ttl_seconds: int
    confirmation_hmac_key: str
    write_enabled: bool
    write_kubernetes_api_url: str
    write_kubernetes_bearer_token: str
    audit_sink: str
    audit_file: str

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
        intent_timeout_seconds=_positive_float("CHATOPS_INTENT_TIMEOUT_SECONDS", 35),
        mcp_timeout_seconds=_bounded_float("CHATOPS_MCP_TIMEOUT_SECONDS", 15, 0.1, 20),
        mcp_max_response_bytes=_bounded_int(
            "CHATOPS_MCP_MAX_RESPONSE_BYTES", 65536, 1024, 262144
        ),
        kubernetes_namespace=_required_namespace("CHATOPS_KUBERNETES_NAMESPACE"),
        kubernetes_max_pods=_bounded_int("CHATOPS_KUBERNETES_MAX_PODS", 10, 1, 20),
        kubernetes_restart_threshold=_bounded_int(
            "CHATOPS_KUBERNETES_RESTART_THRESHOLD", 3, 1, 100
        ),
        insighthub_api_url=os.getenv(
            "CHATOPS_INSIGHTHUB_API_URL", "http://127.0.0.1:8000"
        ).strip(),
        prometheus_url=os.getenv(
            "CHATOPS_PROMETHEUS_URL", "http://127.0.0.1:9090"
        ).strip(),
        kubernetes_kubeconfig=os.getenv(
            "CHATOPS_KUBERNETES_KUBECONFIG", ""
        ).strip(),
        slack_reply_timeout_seconds=_positive_float(
            "CHATOPS_SLACK_REPLY_TIMEOUT_SECONDS", 10
        ),
        slack_bot_token=os.getenv("SLACK_BOT_TOKEN", "").strip(),
        slack_api_base_url=os.getenv("SLACK_API_BASE_URL", "").strip().rstrip("/"),
        approver_user_ids=_identifier_set("CHATOPS_APPROVER_USER_IDS"),
        scale_deployment_allowlist=_deployment_set(
            "CHATOPS_SCALE_DEPLOYMENT_ALLOWLIST"
        ),
        approval_ttl_seconds=_bounded_int(
            "CHATOPS_APPROVAL_TTL_SECONDS", 900, 60, 3600
        ),
        confirmation_ttl_seconds=_bounded_int(
            "CHATOPS_CONFIRMATION_TTL_SECONDS", 60, 15, 300
        ),
        confirmation_hmac_key=os.getenv("CHATOPS_CONFIRMATION_HMAC_KEY", "").strip(),
        write_enabled=_boolean("CHATOPS_WRITE_ENABLED", False),
        write_kubernetes_api_url=os.getenv(
            "CHATOPS_WRITE_KUBERNETES_API_URL", ""
        ).strip().rstrip("/"),
        write_kubernetes_bearer_token=os.getenv(
            "CHATOPS_WRITE_KUBERNETES_BEARER_TOKEN", ""
        ).strip(),
        audit_sink=_audit_sink("CHATOPS_AUDIT_SINK"),
        audit_file=os.getenv("CHATOPS_AUDIT_FILE", "").strip(),
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


def _boolean(name: str, default: bool) -> bool:
    """Read an explicit feature flag without accepting ambiguous values."""

    value = os.getenv(name, "1" if default else "0").strip()
    if value == "1":
        return True
    if value == "0":
        return False
    raise ValueError(f"{name} must be 0 or 1")


def _audit_sink(name: str) -> str:
    """Accept only the two operator-configured audit sink types."""

    value = os.getenv(name, "stdout").strip()
    if value not in {"stdout", "file"}:
        raise ValueError(f"{name} must be stdout or file")
    if value == "file" and not os.getenv("CHATOPS_AUDIT_FILE", "").strip():
        raise ValueError("CHATOPS_AUDIT_FILE is required for file audit sink")
    return value


def _identifier_set(name: str) -> frozenset[str]:
    """Read operator-owned Slack identities, never values from an event."""

    values = [item.strip() for item in os.getenv(name, "").split(",") if item.strip()]
    if any(not item.isascii() or not item.replace("-", "").isalnum() for item in values):
        raise ValueError(f"{name} contains an invalid identity")
    return frozenset(values)


def _deployment_set(name: str) -> frozenset[str]:
    """Read a fixed deployment allowlist for the sole write action."""

    values = [item.strip() for item in os.getenv(name, "").split(",") if item.strip()]
    allowed = set("abcdefghijklmnopqrstuvwxyz0123456789-")
    if any(
        len(item) > 63
        or item[0] == "-"
        or item[-1] == "-"
        or any(character not in allowed for character in item)
        for item in values
    ):
        raise ValueError(f"{name} contains an invalid deployment name")
    return frozenset(values)
