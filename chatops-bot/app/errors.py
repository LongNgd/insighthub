"""Controlled, sanitized errors for the ChatOps asynchronous pipeline."""


class ChatopsError(Exception):
    """Base exception whose code is safe to record in audit logs."""

    code = "chatops_error"


class QueueUnavailable(ChatopsError):
    """Raised when Redis cannot durably accept an authenticated event."""

    code = "queue_unavailable"


class EventValidationError(ChatopsError):
    """Raised for an authenticated payload that has no usable event identity."""

    code = "invalid_event"


class PermanentProcessingError(ChatopsError):
    """A failure that cannot become healthy by retrying the same job."""

    code = "permanent_processing_error"


class TransientProcessingError(ChatopsError):
    """A bounded-retry failure from an approved worker dependency."""

    code = "transient_processing_error"
