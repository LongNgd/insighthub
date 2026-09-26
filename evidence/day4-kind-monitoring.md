# Day 4 kind monitoring: ServiceMonitor/exporter runtime evidence

Ngày kiểm tra: 2026-09-26. Context: `kind-insighthub`; namespace ứng dụng: `insighthub-prod`; namespace Prometheus: `monitoring`. Helm release `insighthub` revision 13, status `deployed`.

## Static gates và rollout

| Lệnh | Kết quả |
| --- | --- |
| `helm lint helm/insighthub -f helm/insighthub/values-local.yaml` | `1 chart(s) linted, 0 chart(s) failed` |
| `helm lint helm/insighthub -f helm/insighthub/values-eks.yaml` | `1 chart(s) linted, 0 chart(s) failed` |
| `helm template insighthub helm/insighthub -n insighthub-prod -f helm/insighthub/values-local.yaml` | exit 0; manifest đã review tại `evidence/day4-kind-monitoring-preview.yaml` với API image tag của release hiện có |
| `helm template insighthub helm/insighthub -n insighthub-prod -f helm/insighthub/values-eks.yaml` | exit 0; exporter local không bật trên EKS |
| `git diff --check` | exit 0 |
| `kubectl get servicemonitor -n insighthub-prod` | Có `insighthub-api`, `insighthub-web`, `insighthub-worker`, `insighthub-postgres-exporter`, `insighthub-redis-exporter` |
| `helm status insighthub -n insighthub-prod` | revision 13, `deployed`; bảy pod ứng dụng/exporter `1/1 Running` |
| `kubectl get pvc -n insighthub-prod` | `insighthub-postgres-data` và `insighthub-redis-data` vẫn `Bound` với volume ID cũ |

Prometheus CR `kube-prom-stack-kube-prome-prometheus` có `serviceMonitorNamespaceSelector: {}` và `serviceMonitorSelector.matchLabels.release: kube-prom-stack`. Cả năm ServiceMonitor có nhãn đó, selector khớp Service metadata và endpoint dùng đúng tên port `http` hoặc `metrics`.

## Prometheus targets và sample metric

Đọc `/api/v1/targets` qua port-forward localhost đến `svc/kube-prom-stack-kube-prome-prometheus` cổng 9090. Cả năm active target có `health: up`, `lastError: ""`. `/api/v1/status/config` có đủ năm scrape job sau đây. PromQL là instant query qua `/api/v1/query`, không dùng metric `up` làm bằng chứng duy nhất.

| Thành phần | Nguồn / ServiceMonitor job | PromQL và sample thực tế | Target |
| --- | --- | --- | --- |
| API | FastAPI `/metrics`; `serviceMonitor/insighthub-prod/insighthub-api/0` | `insighthub_documents_total{job="insighthub-api"}` → 3 series, giá trị `0`, `7`, `0` | UP |
| Web | Next.js `/metrics`; `serviceMonitor/insighthub-prod/insighthub-web/0` | `insighthub_web_nodejs_eventloop_lag_seconds{job="insighthub-web"}` → 1 series, `0.002376587` | UP |
| Ingestion worker | HTTP metrics port 9101; `serviceMonitor/insighthub-prod/insighthub-worker/0` | `insighthub_worker_ready{job="insighthub-worker"}` → 1 series, `1` | UP |
| PostgreSQL/pgvector | `postgres_exporter` 9187 kết nối `insighthub-postgres:5432`; `serviceMonitor/insighthub-prod/insighthub-postgres-exporter/0` | `pg_up{job="insighthub-postgres-exporter"}` → `1`; `pg_stat_database_numbackends{job="insighthub-postgres-exporter"}` → 4 series, gồm giá trị `6` | UP |
| Redis | `redis_exporter` 9121 kết nối `insighthub-redis:6379`; `serviceMonitor/insighthub-prod/insighthub-redis-exporter/0` | `redis_up{job="insighthub-redis-exporter"}` → `1`; `redis_connected_clients{job="insighthub-redis-exporter"}` → `2` | UP |

Exporter theo dõi đúng PostgreSQL và Redis đang chạy trong namespace `insighthub-prod`. pgvector là extension trong PostgreSQL này; lần kiểm tra thu metric không đo riêng trạng thái extension hoặc hiệu năng vector index.

## Lệnh kiểm tra lại

```bash
kubectl config current-context
kubectl get pods,svc,servicemonitor,pvc -n insighthub-prod
helm status insighthub -n insighthub-prod --show-resources
kubectl port-forward -n monitoring svc/kube-prom-stack-kube-prome-prometheus 19090:9090 --address 127.0.0.1
curl -fsS http://127.0.0.1:19090/api/v1/targets
curl -fsSG --data-urlencode 'query=insighthub_documents_total{job="insighthub-api"}' http://127.0.0.1:19090/api/v1/query
curl -fsSG --data-urlencode 'query=insighthub_web_nodejs_eventloop_lag_seconds{job="insighthub-web"}' http://127.0.0.1:19090/api/v1/query
curl -fsSG --data-urlencode 'query=insighthub_worker_ready{job="insighthub-worker"}' http://127.0.0.1:19090/api/v1/query
curl -fsSG --data-urlencode 'query=pg_stat_database_numbackends{job="insighthub-postgres-exporter"}' http://127.0.0.1:19090/api/v1/query
curl -fsSG --data-urlencode 'query=redis_connected_clients{job="insighthub-redis-exporter"}' http://127.0.0.1:19090/api/v1/query
```

Trong lần triển khai, `kind load` với cả bốn image một lượt không import được manifest đa kiến trúc của postgres exporter. Hai app image được nạp riêng; hai exporter được kéo theo digest vào node kind. Hai upgrade đầu thất bại vì `--reuse-values` không thêm chart defaults mới. Sau khi sửa giá trị port worker và dùng `--reset-then-reuse-values`, Redis exporter phát hiện password-file yêu cầu JSON; template được sửa dùng `REDIS_PASSWORD` từ Secret reference. Release được rollback về revision 8 trước lần upgrade cuối, rồi revision 13 triển khai thành công. Không xóa PVC hoặc dữ liệu.
