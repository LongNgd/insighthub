# Day 4 Grafana dashboard — kind runtime evidence

Observed on 2026-09-27, context `kind-insighthub`, application namespace `insighthub-prod`, monitoring namespace `monitoring`. Helm release `insighthub` revision **14** deployed at `2026-09-27T03:36:09.693209402Z`. This is a local fixture run; it does not attest EKS or real provider billing.

## Deployment and static checks

- `helm lint helm/insighthub -f helm/insighthub/values-local.yaml`: 1 chart linted, 0 failed.
- `helm template insighthub helm/insighthub -n insighthub-prod -f helm/insighthub/values-local.yaml --set-string images.api.tag=day4-dashboard-r1 --set-string images.worker.tag=day4-dashboard-r1 --set-string images.web.tag=day4-metrics-r1`: PASS. Reviewed manifest: one added dashboard ConfigMap, two changed Deployment image tags, no removed object and no Secret object.
- API unit suite: 40 tests PASS. Worker metrics test: 1 PASS. `git diff --check`: PASS.
- `kind load docker-image` loaded `insighthub-api:day4-dashboard-r1` and `insighthub-worker:day4-dashboard-r1`; `helm upgrade --reset-then-reuse-values` applied revision 14. Both Deployment rollouts succeeded. No PVC, database schema or Secret was changed.
- `kubectl get configmap insighthub-day4-dashboard -n insighthub-prod`: dashboard UID `insighthub-day4`, 12 panels, 13 PromQL targets.

## Runtime telemetry

`python scripts/smoke-k8s-local.py --api-url http://127.0.0.1:18000 --web-url http://127.0.0.1:13000 --poll-timeout 45` returned `PASS`: upload HTTP 202, document became ready, chat succeeded, `/metrics` returned numeric samples. The smoke document remains in the local database; no document content is recorded here.

Prometheus `/api/v1/targets` returned `health: up` and empty `lastError` for all five jobs: `insighthub-api`, `insighthub-web`, `insighthub-worker`, `insighthub-postgres-exporter`, `insighthub-redis-exporter`. Querying each dashboard expression through `/api/v1/query` with Grafana's rate interval expanded to `5m` returned:

| Panel | Source metric | Result series |
| --- | --- | ---: |
| RED request rate | `insighthub_http_requests_total` | 1 |
| RED 5xx percent | `insighthub_http_requests_total` | 1 |
| RED mean duration | `insighthub_http_request_duration_seconds_sum/count` | 1 |
| ARQ queue entries | `insighthub_worker_queue_entries` + probe success | 1 |
| LLM token usage | provider-reported / word-estimated counters | 0 / 2 |
| HTTP latency p95 | `insighthub_http_request_duration_seconds_bucket` | 1 |
| Estimated LLM cost | `insighthub_llm_estimated_cost_usd_total` | 1 |
| CPU utilization / limit | cAdvisor / kube-state-metrics | 7 |
| Memory utilization / limit | cAdvisor / kube-state-metrics | 7 |
| CPU throttling | cAdvisor | 9 |
| Container restarts | kube-state-metrics | 7 |
| Deploy generation | kube-state-metrics | 3 |

The provider-reported token series is absent in fixture mode by design; the estimated series has real samples from the smoke chat. The cost series is `0` for a fixture call because no external LLM provider was charged. `insighthub_worker_queue_probe_success=1` and `insighthub_worker_queue_entries=0` after the job completed. `ZCARD` counts ARQ queue entries, including deferred and in-progress jobs, rather than waiting-only jobs.

## Grafana UI and deploy marker

Dashboard URL through the local port-forward: `http://127.0.0.1:13001/d/insighthub-day4/insighthub-day-4-c2b7-red-use`. Grafana API returned UID `insighthub-day4` and 12 panels. The deployment marker was written using `scripts/annotate-day4-deploy.py` with Helm revision 14's actual timestamp; Grafana API returned annotation ID `1`, time `1790480169693` ms, text `InsightHub Helm revision 14`. The UI shows its vertical marker with the `Deploys` layer enabled. Browser DOM inspection found all 12 panel headings and **no “No data” text**.

Screenshots from the running dashboard:

- [Top panels and deploy marker](day4-dashboard-top.jpg)
- [Token usage and HTTP p95](day4-dashboard-middle.jpg)
- [Memory utilization and CPU throttling](day4-dashboard-resources.jpg)
- [Container restarts and deploy generation](day4-dashboard-bottom.jpg)

## Recheck

From the repo root in WSL, activate `.venv`, then run:

```sh
kubectl config current-context
kubectl get configmap insighthub-day4-dashboard -n insighthub-prod
kubectl get pods,deploy -n insighthub-prod
kubectl -n monitoring port-forward svc/kube-prom-stack-kube-prome-prometheus 19090:9090 --address 127.0.0.1
kubectl -n monitoring port-forward svc/kube-prom-stack-grafana 13001:80 --address 127.0.0.1
```

Use separate terminals for the two port-forwards. Inspect `http://127.0.0.1:19090/api/v1/targets` and the dashboard URL above. The dashboard JSON in `helm/insighthub/files/day4-dashboard.json` contains every exact PromQL expression; replace `$__rate_interval` with `5m` when using the Prometheus HTTP API directly. Use the Grafana time range containing the release timestamp to see the annotation.

Limits: this confirms kind with fixture generation, not real provider token billing or pricing. Real mode requires explicit nonzero `LLM_INPUT_USD_PER_MILLION_TOKENS` and `LLM_OUTPUT_USD_PER_MILLION_TOKENS` for a cost sample. The local URL requires a running localhost port-forward.
