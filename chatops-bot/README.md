# ChatOps - Day 5

`POST /slack/events` verifies the exact Slack raw body and timestamp before it
parses a payload. A non-self event is normalized, deduplicated in Redis, and
submitted to ARQ before the HTTP adapter returns `{"ok": true}`. It never calls
the intent router, MCP, AI, or Slack reply API on the request path.

Run the worker separately after setting the environment:

```sh
arq app.worker.WorkerSettings
```

Required transport and queue configuration:

- `SLACK_SIGNING_SECRET`, `SLACK_BOT_USER_ID`
- `CHATOPS_REDIS_URL`, `CHATOPS_QUEUE_NAME`
- `SLACK_BOT_TOKEN`, `SLACK_API_BASE_URL`

Optional bounded-operation settings are `CHATOPS_QUEUE_TIMEOUT_SECONDS`,
`CHATOPS_WORKER_MAX_TRIES` (1–3), `CHATOPS_RETRY_BASE_SECONDS`,
`CHATOPS_RETRY_MAX_SECONDS`, `CHATOPS_DEDUP_TTL_SECONDS`,
`CHATOPS_REPLY_TTL_SECONDS`, `CHATOPS_INTENT_TIMEOUT_SECONDS`,
`CHATOPS_MCP_TIMEOUT_SECONDS`, and `CHATOPS_SLACK_REPLY_TIMEOUT_SECONDS`.

Dedup keys use a SHA-256 identity over team/event ID; Redis performs the initial
`SET NX EX` claim atomically. A failed enqueue releases only its own claim. The
worker retries classified transient failures at most three times and records an
opaque reply state plus stable `client_msg_id`, preventing a completed reply
from being sent again after a retry or restart. Audit records contain only
opaque IDs and sanitized outcome categories.

The allowlist currently accepts only the Day 5 read-only intent forms: health,
documents ingested today, and failed pods. It does not turn user text into tool
names or arguments. Unit tests use local doubles and do not establish Slack LIVE
evidence. See [specification section 9](../Running-Project-Specification-Student.md).
