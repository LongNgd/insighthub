"""Raw-body Slack request authentication helpers."""

import hashlib
import hmac
import time


MAX_SLACK_TIMESTAMP_SKEW_SECONDS = 300


class SlackAuthenticationError(Exception):
    """Raised when a Slack request cannot be authenticated safely."""


def verify_slack_request(
    *,
    raw_body: bytes,
    signature: str | None,
    timestamp: str | None,
    signing_secret: str,
    now: float | None = None,
) -> None:
    """Verify Slack v0 HMAC and the bounded replay window for raw bytes."""

    if not signature or not timestamp or not signing_secret:
        raise SlackAuthenticationError()
    if not timestamp.isascii() or not timestamp.isdecimal():
        raise SlackAuthenticationError()

    try:
        timestamp_value = int(timestamp)
    except ValueError as error:
        raise SlackAuthenticationError() from error
    current_time = time.time() if now is None else now
    if abs(current_time - timestamp_value) > MAX_SLACK_TIMESTAMP_SKEW_SECONDS:
        raise SlackAuthenticationError()

    signature_base = b"v0:" + timestamp.encode("ascii") + b":" + raw_body
    expected_signature = "v0=" + hmac.new(
        signing_secret.encode("utf-8"),
        signature_base,
        hashlib.sha256,
    ).hexdigest()
    if not signature.isascii() or not hmac.compare_digest(expected_signature, signature):
        raise SlackAuthenticationError()
