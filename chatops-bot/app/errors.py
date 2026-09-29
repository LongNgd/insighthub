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


class McpUnavailable(TransientProcessingError):
    """An approved read-only MCP capability did not complete before its deadline."""

    code = "mcp_unavailable"


class McpSchemaError(PermanentProcessingError):
    """An MCP response did not meet the narrow projection expected by the bot."""

    code = "mcp_schema_error"


class PolicyDenied(PermanentProcessingError):
    """Raised when server-side authorization rejects a requested action."""

    code = "policy_denied"


class PolicyUnavailable(TransientProcessingError):
    """Raised when durable authorization state cannot be reached."""

    code = "policy_unavailable"


class MutationExecutorUnavailable(PermanentProcessingError):
    """Raised before a write when its distinct executor is not configured."""

    code = "mutation_executor_unavailable"


class MutationOutcomeUnknown(PermanentProcessingError):
    """A mutation might have started; it must be reconciled, never retried."""

    code = "reconciliation_required"
