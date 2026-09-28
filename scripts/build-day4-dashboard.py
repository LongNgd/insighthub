"""Generate the provisioned Day 4 dashboard using only bounded Prometheus labels."""

import json
from pathlib import Path


NAMESPACE = "insighthub-prod"
PODS = 'pod=~"insighthub-(api|web|worker|postgres|redis).*"'
DATA_SOURCE = {"type": "prometheus", "uid": "prometheus"}


def panel(panel_id: int, title: str, queries: list[tuple[str, str]], unit: str,
          description: str = "") -> dict:
    row = (panel_id - 1) // 2
    column = (panel_id - 1) % 2
    return {
        "id": panel_id,
        "title": title,
        "description": description,
        "type": "timeseries",
        "datasource": DATA_SOURCE,
        "gridPos": {"h": 8, "w": 12, "x": column * 12, "y": row * 8},
        "fieldConfig": {"defaults": {"unit": unit}, "overrides": []},
        "options": {"legend": {"displayMode": "list", "placement": "bottom"},
                    "tooltip": {"mode": "multi"}},
        "targets": [
            {"refId": chr(65 + i), "expr": expression, "legendFormat": legend,
             "datasource": DATA_SOURCE}
            for i, (expression, legend) in enumerate(queries)
        ],
    }


http = f'insighthub_http_requests_total{{namespace="{NAMESPACE}",endpoint!="/metrics"}}'
http_5xx = f'insighthub_http_requests_total{{namespace="{NAMESPACE}",endpoint!="/metrics",status=~"5.."}}'
cpu = f'container_cpu_usage_seconds_total{{namespace="{NAMESPACE}",{PODS},container!="",image!=""}}'
limits_cpu = f'kube_pod_container_resource_limits{{namespace="{NAMESPACE}",{PODS},resource="cpu",unit="core"}}'
memory = f'container_memory_working_set_bytes{{namespace="{NAMESPACE}",{PODS},container!="",image!=""}}'
limits_memory = f'kube_pod_container_resource_limits{{namespace="{NAMESPACE}",{PODS},resource="memory",unit="byte"}}'
throttled = f'container_cpu_cfs_throttled_periods_total{{namespace="{NAMESPACE}",{PODS},container!="",image!=""}}'
periods = f'container_cpu_cfs_periods_total{{namespace="{NAMESPACE}",{PODS},container!="",image!=""}}'

panels = [
    panel(1, "RED · Request rate", [(f"sum by (endpoint) (rate({http}[$__rate_interval]))", "{{endpoint}}")], "reqps"),
    panel(2, "RED · 5xx errors", [(
        f"100 * (sum(rate({http_5xx}[$__rate_interval])) or 0 * sum(rate({http}[$__rate_interval]))) / sum(rate({http}[$__rate_interval]))",
        "5xx / all requests")], "percent", "A zero is derived only when total request samples exist."),
    panel(3, "RED · Mean HTTP duration", [(
        f"sum(rate(insighthub_http_request_duration_seconds_sum{{namespace=\"{NAMESPACE}\",endpoint!=\"/metrics\"}}[$__rate_interval])) / sum(rate(insighthub_http_request_duration_seconds_count{{namespace=\"{NAMESPACE}\",endpoint!=\"/metrics\"}}[$__rate_interval]))",
        "mean")], "s"),
    panel(4, "Worker · ARQ queue entries", [(
        f'insighthub_worker_queue_entries{{namespace="{NAMESPACE}"}} and on (job, instance) (insighthub_worker_queue_probe_success{{namespace="{NAMESPACE}"}} == 1)',
        "entries")], "short",
          "ZCARD includes queued, deferred and in-progress jobs; probe success is checked separately."),
    panel(5, "LLM · Token usage", [
        (f'sum by (direction) (rate(insighthub_llm_tokens_total{{namespace="{NAMESPACE}"}}[$__rate_interval]))', "provider {{direction}}"),
        (f'sum by (direction) (rate(insighthub_llm_estimated_tokens_total{{namespace="{NAMESPACE}"}}[$__rate_interval]))', "estimated {{direction}}"),
    ], "short", "Estimated token counts are word-based and are not billing usage."),
    panel(6, "RED · HTTP latency p95", [(
        f'histogram_quantile(0.95, sum by (le) (rate(insighthub_http_request_duration_seconds_bucket{{namespace="{NAMESPACE}",endpoint!="/metrics"}}[$__rate_interval])))',
        "p95")], "s"),
    panel(7, "LLM · Estimated cost", [(
        f'sum by (provider, usage_source) (insighthub_llm_estimated_cost_usd_total{{namespace="{NAMESPACE}"}})',
        "{{provider}} / {{usage_source}}")], "currencyUSD",
          "Cumulative USD estimate from configured per-million-token rates. Fixture is zero provider charge; real mode requires rates."),
    panel(8, "USE · CPU utilization / limit", [(
        f'100 * sum by (pod) (rate({cpu}[$__rate_interval])) / on (pod) sum by (pod) ({limits_cpu})',
        "{{pod}}")], "percent"),
    panel(9, "USE · Memory utilization / limit", [(
        f'100 * sum by (pod) ({memory}) / on (pod) sum by (pod) ({limits_memory})',
        "{{pod}}")], "percent"),
    panel(10, "USE · CPU throttling", [(
        f'100 * sum by (pod) (rate({throttled}[$__rate_interval])) / on (pod) sum by (pod) (rate({periods}[$__rate_interval]))',
        "{{pod}}")], "percent"),
    panel(11, "USE · Container restarts", [(
        f'sum by (pod) (kube_pod_container_status_restarts_total{{namespace="{NAMESPACE}",{PODS}}})',
        "{{pod}}")], "short"),
    panel(12, "Deploy · Generation", [(
        f'kube_deployment_metadata_generation{{namespace="{NAMESPACE}",deployment=~"insighthub-(api|web|worker)"}}',
        "{{deployment}}")], "short", "Release events appear as Grafana annotations on all panels."),
]

dashboard = {
    "uid": "insighthub-day4",
    "title": "InsightHub Day 4 · RED / USE",
    "tags": ["insighthub", "day4", "red", "use"],
    "timezone": "browser",
    "schemaVersion": 39,
    "version": 1,
    "refresh": "15s",
    "time": {"from": "now-1h", "to": "now"},
    "annotations": {"list": [{"builtIn": 1, "datasource": {"type": "grafana", "uid": "-- Grafana --"},
                               "enable": True, "hide": False, "iconColor": "rgba(0, 211, 255, 1)",
                               "name": "Deploys", "type": "dashboard"}]},
    "panels": panels,
}

output = Path(__file__).resolve().parents[1] / "helm/insighthub/files/day4-dashboard.json"
output.write_text(json.dumps(dashboard, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(output)
