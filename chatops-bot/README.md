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
- `SLACK_BOT_TOKEN`, `SLACK_API_BASE_URL`. `SLACK_BOT_TOKEN` is read only
  from the environment. Never place it in source, an image layer, or evidence.

Optional bounded-operation settings are `CHATOPS_QUEUE_TIMEOUT_SECONDS`,
`CHATOPS_WORKER_MAX_TRIES` (1–3), `CHATOPS_RETRY_BASE_SECONDS`,
`CHATOPS_RETRY_MAX_SECONDS`, `CHATOPS_DEDUP_TTL_SECONDS`,
`CHATOPS_REPLY_TTL_SECONDS`, `CHATOPS_INTENT_TIMEOUT_SECONDS`,
`CHATOPS_MCP_TIMEOUT_SECONDS`, and `CHATOPS_SLACK_REPLY_TIMEOUT_SECONDS`.

## Local and container runtime

The local Uvicorn + ngrok path is the Day 5 lab default. Keep the ignored
`chatops-bot/.env` file local, load it into the terminal, then run the HTTP
adapter and worker separately:

```sh
set -a && . ./.env && set +a
uvicorn app.main:app --host 127.0.0.1 --port 8080
# separate terminal, with the same environment
arq app.worker.WorkerSettings
```

Use ngrok only to expose the Uvicorn listener to Slack; never include a token
in an ngrok URL or commit it. The live bot token is supplied by the ignored
environment file for this local lab.

The image includes Python, the pinned Node runtime, custom MCP source and the
pinned Kubernetes MCP package. Build it from the project root so the Docker
build context can be restricted by `Dockerfile.dockerignore`:

```sh
docker build -f chatops-bot/Dockerfile -t insighthub-chatops:local .
```

For a Linux/WSL host deployment, pass runtime values through an external
environment file or secret store and use host networking only when local API
and Prometheus port-forwards are intentionally part of the lab. Do not pass
secrets with `--build-arg`.

For Kubernetes, create the Slack runtime secret out of band (the command does
not write its values to the repository), then reference it from the deployment
environment:

```sh
kubectl -n insighthub-prod create secret generic chatops-slack-runtime \
  --from-literal=SLACK_SIGNING_SECRET="$SLACK_SIGNING_SECRET" \
  --from-literal=SLACK_BOT_TOKEN="$SLACK_BOT_TOKEN"
```

Use a separately managed Secret or external-secret mechanism for the remaining
runtime values, including the read-only kubeconfig. Never put bot tokens,
signing secrets, kubeconfig, or Redis credentials in a Helm values file.

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

The local-lab worker uses a source-owned STDIO bridge at
`../tools/mcp/src/chatops-stdio.mjs`; it does not read Codex Desktop
configuration and it never accepts a server command, MCP tool, namespace, or
arguments from Slack. The bridge starts only the pinned local custom MCP and
`kubernetes-mcp-server@0.0.67`. It passes the Kubernetes server
`--read-only`, `--disable-destructive`, `--disable-multi-cluster`,
`--cluster-provider=kubeconfig`, `--toolsets=core`, and an explicit kubeconfig
path. RBAC remains the final enforcement layer.

Operators configure these non-secret paths/endpoints from local deployment
configuration; never commit kubeconfig content or credentials:

- `CHATOPS_INSIGHTHUB_API_URL` (default `http://127.0.0.1:8000`) and
  `CHATOPS_PROMETHEUS_URL` (default `http://127.0.0.1:9090`). The existing
  custom MCP permits only loopback origins.
- `CHATOPS_KUBERNETES_KUBECONFIG`: an absolute path to a kubeconfig that uses
  the `mcp-readonly` ServiceAccount. It is required for the pod intent.
- `CHATOPS_KUBERNETES_NAMESPACE`: operator-owned namespace (default
  `insighthub-prod`), never derived from a Slack message.
- `CHATOPS_MCP_TIMEOUT_SECONDS` (0.1–20; default 15),
  `CHATOPS_MCP_MAX_RESPONSE_BYTES` (1024–262144),
  `CHATOPS_KUBERNETES_MAX_PODS` (1–20), and
  `CHATOPS_KUBERNETES_RESTART_THRESHOLD` (1–100).

Audit output defaults to `stdout`. Set `CHATOPS_AUDIT_SINK=file` together with
`CHATOPS_AUDIT_FILE` to use an operator-selected JSONL file. The sink is checked
before every MCP call and mutation dispatch: a failed check prevents the call.
Records contain only correlation IDs, allowlisted action/tool/summary codes and
safe approval metadata; raw Slack, MCP, document and credential data are never
written.

The only worker capabilities are `insighthub_health`,
`prometheus_summary` with `requests_5m`/`errors_5m`,
`insighthub_ingest_count_today_utc`, and Kubernetes
`pods_list_in_namespace` scoped to the configured namespace. The router
rejects all other Slack text; it never accepts tool names, PromQL, URLs,
namespaces, shell commands, or mutation requests.

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
