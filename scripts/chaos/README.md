# Day 4 fixture incidents on kind

This lab uses the local fixture only. The chart defaults to fault control off;
`values-local.yaml` mounts an `off` ConfigMap into the API and worker. Control
data expires after at most 15 minutes, and malformed or missing data is off.
`values-eks.yaml` does not enable the hook. No API endpoint, database state or
ingestion transaction is changed by the hook.

## Gates before kind changes

Work in WSL at the repository root and activate the existing `.venv` before
every shell session. Review `git diff`, run `make test-backend`, the worker test,
the driver test, `promtool check/test rules`, `helm lint`, and `helm template`.
Compare the rendered manifest with `helm get manifest insighthub -n
insighthub-prod`. The intended rollout is API and worker only; the new
`insighthub-day4-chaos` ConfigMap starts `off`. Confirm exact image tags and
current release values before any Helm upgrade. Changing kind needs separate
approval.

## Runtime sequence after separate approval

Open three WSL terminals with localhost-only port-forwards:

```sh
kubectl --context kind-insighthub -n insighthub-prod port-forward svc/insighthub-api 18000:8000 --address 127.0.0.1
kubectl --context kind-insighthub -n monitoring port-forward svc/kube-prom-stack-kube-prome-prometheus 19090:9090 --address 127.0.0.1
kubectl --context kind-insighthub -n monitoring port-forward svc/kube-prom-stack-kube-prome-alertmanager 19093:9093 --address 127.0.0.1
```

If the three baselines are not ready, run `python scripts/chaos/run-day4.py
baseline --execute` after confirming at least one `ready` fixture document. It
sends one ordinary fixture chat per minute for 70 minutes. Recheck all three
`baseline_ready=1`, `band_upper` present, five targets UP, and the three
alerts inactive before *each* incident.

After approval for the incident traffic, run each incident without a silence.
The driver checks Alertmanager and stops if any active silence exists:

```sh
python scripts/chaos/run-day4.py latency --execute
```

Repeat sequentially with `backlog` and `errors`. The driver patches only
`insighthub-day4-chaos`, waits for ConfigMap
projection, sends bounded fixture traffic, observes `pending`/`firing`, and
always patches the control back to `off` after traffic. If it is interrupted,
the expiry also disables the fault. `python scripts/chaos/run-day4.py off
--execute` is the manual stop. Worker backlog uses a serial gate and keeps the
worker metrics loop running. It uploads at most 30 small fixture documents and
does not delete any documents. The driver uses 15 seconds per job to keep jobs
waiting on the serial gate below ARQ's five-minute job timeout; it also waits
for every accepted fixture document to reach `ready` after the queue metric
recovers.

The anomaly route sends firing and resolved notifications to the configured
Slack webhook. Its title and text include alert name, namespace, summary,
description and timestamps. Confirm at least one actual notification in
`#alerts` with the corresponding Prometheus firing time to satisfy MH6.

## RCA evidence

For each alert, save the fault activation, Prometheus `pending`/`firing`, fault
off and recovery times. Query `/api/v1/query_range` for the affected `current`,
`band_upper`, source metric and relevant supporting metrics. Inspect workload
readiness, events and recent rollout through the read-only Kubernetes MCP.
Codex uses the Prometheus and Kubernetes MCP results to consider competing
hypotheses, then writes one `rca-reports/incident-N.json` with `incident_id`,
`started_at`, `ended_at`, `hypotheses`, `samples` and a reviewed conclusion.
Each sample contains `metric`, `labels`, `timestamp` (RFC3339) and finite numeric
`value` that matches live Prometheus. State that the cause was an injected
fixture fault; do not describe it as a real provider outage. Keep raw document
content, secrets, tokens and provider bodies out of evidence. If the target
alert never fires or recovery cannot be verified, record FAIL and leave RCA
unverified.
