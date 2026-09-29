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

## Permission enforcement

The worker owns a fixed action catalog. The three existing diagnostics are the
only automatically executable capabilities. A Slack request in the exact form
`scale <deployment> to <replicas>` can only create an approval request when the
deployment appears in `CHATOPS_SCALE_DEPLOYMENT_ALLOWLIST`; it never selects a
namespace, tool, URL, or Kubernetes verb. A separately signed Slack interaction
from an identity in `CHATOPS_APPROVER_USER_IDS` may approve it, provided that it
is not the requester. Redis persists and atomically consumes the bound approval
record before the sole write executor can run.

The optional writer is disabled by default. Operators must explicitly set
`CHATOPS_WRITE_ENABLED=1`, `CHATOPS_WRITE_KUBERNETES_API_URL`, and
`CHATOPS_WRITE_KUBERNETES_BEARER_TOKEN` from deployment configuration or a
Kubernetes Secret. Its identity is represented by
`../kubernetes/chatops/chatops-scale-writer.yaml`, which grants only
`patch`/`update` on `apps/deployments/scale` in `insighthub-prod`. It is not the
`mcp-readonly` identity and has no delete permission.

Approval records use `CHATOPS_APPROVAL_TTL_SECONDS` (default 900 seconds).
The destructive-action framework is default-deny because no destructive action
is registered. A future operator-approved destructive capability must also set
`CHATOPS_CONFIRMATION_HMAC_KEY` and use an opaque confirmation token with
`CHATOPS_CONFIRMATION_TTL_SECONDS` (default 60 seconds); neither token material
nor secret values are written to audit logs.

## Read-only MCP runtime

The worker has a separate JSON-RPC MCP transport; it does not read the Codex
desktop MCP configuration or inherit a kubeconfig. Operators configure the
following values from deployment configuration/Secrets (never commit values):

- `CHATOPS_INSIGHTHUB_MCP_URL` and optional
  `CHATOPS_INSIGHTHUB_MCP_BEARER_TOKEN`: the fixed InsightHub read-only MCP
  transport exposing health, Prometheus summaries and UTC ingest count.
- `CHATOPS_KUBERNETES_MCP_URL` and optional
  `CHATOPS_KUBERNETES_MCP_BEARER_TOKEN`: the dedicated read-only Kubernetes
  MCP transport authenticated as the `mcp-readonly` ServiceAccount.
- `CHATOPS_KUBERNETES_NAMESPACE`: operator-owned namespace (default
  `insighthub-prod`), never derived from a Slack message.
- `CHATOPS_MCP_TIMEOUT_SECONDS` (0.1–10),
  `CHATOPS_MCP_MAX_RESPONSE_BYTES` (1024–262144),
  `CHATOPS_KUBERNETES_MAX_PODS` (1–20), and
  `CHATOPS_KUBERNETES_RESTART_THRESHOLD` (1–100).

The only worker capabilities are `insighthub_health`,
`prometheus_summary` with `requests_5m`/`errors_5m`,
`insighthub_ingest_count_today_utc`, and Kubernetes `get_pods` scoped to the
configured namespace. The router rejects all other Slack text; it never accepts
tool names, PromQL, URLs, namespaces, shell commands, or mutation requests.

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
