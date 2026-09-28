# InsightHub Helm chart

Local kind chạy năm thành phần trong namespace `insighthub-prod`: `web`, `api`, `worker`, PostgreSQL/pgvector và Redis. Chart không tạo Namespace vì namespace local đã do `kubernetes/mcp/mcp-readonly.yaml` tạo; trên EKS namespace và ServiceAccount ứng dụng do Terraform quản lý. Dùng kubeconfig admin của kind cho deploy, không dùng kubeconfig `mcp-readonly`.

## Triển khai local

Chạy từ repo root trong WSL sau `source .venv/bin/activate`. Kiểm tra `kubectl config current-context` là `kind-insighthub` trước các lệnh mutation.

```sh
diff -u <(tr -d '\r' < infra/db/init.sql) helm/insighthub/files/init.sql
helm lint helm/insighthub -f helm/insighthub/values-local.yaml
helm template insighthub helm/insighthub -n insighthub-prod -f helm/insighthub/values-local.yaml > /tmp/insighthub-rendered.yaml

python scripts/create-local-k8s-secret.py
IMAGE_TAG=$(git rev-parse --short=12 HEAD)
docker build -t "insighthub-api:$IMAGE_TAG" ./api
docker build -t "insighthub-worker:$IMAGE_TAG" -f ingestion-worker/Dockerfile .
docker build -t "insighthub-web:$IMAGE_TAG" ./web
kind load docker-image --name insighthub "insighthub-api:$IMAGE_TAG" "insighthub-worker:$IMAGE_TAG" "insighthub-web:$IMAGE_TAG"
helm upgrade --install insighthub helm/insighthub -n insighthub-prod -f helm/insighthub/values-local.yaml --set-string "images.api.tag=$IMAGE_TAG" --set-string "images.worker.tag=$IMAGE_TAG" --set-string "images.web.tag=$IMAGE_TAG" --wait --timeout 8m
```

`create-local-k8s-secret.py` tạo mật khẩu ngẫu nhiên và Secret qua stdin của `kubectl create`; không in giá trị hoặc lưu vào chart/Git. Script không xoay mật khẩu khi Secret đã tồn tại và từ chối tạo mới nếu PVC PostgreSQL cũ còn đó. Không dùng `helm --set` cho credential. Redis dùng AUTH/AOF; PostgreSQL dùng Secret và chỉ chạy `files/init.sql` khi PVC mới. Khi `infra/db/init.sql` thay đổi, đồng bộ `files/init.sql` ở định dạng LF và review diff; không tự xóa PVC để chạy lại init.

## Kiểm tra runtime

```sh
kubectl get pods,deploy,sts,svc,pvc -n insighthub-prod
kubectl rollout status deployment/insighthub-api -n insighthub-prod
kubectl rollout status deployment/insighthub-worker -n insighthub-prod
kubectl rollout status deployment/insighthub-web -n insighthub-prod
kubectl rollout status statefulset/insighthub-postgres -n insighthub-prod
kubectl rollout status statefulset/insighthub-redis -n insighthub-prod
helm status insighthub -n insighthub-prod
kubectl logs deployment/insighthub-api -n insighthub-prod --tail=100
kubectl logs deployment/insighthub-worker -n insighthub-prod --tail=100
```

Ở hai terminal riêng, chạy `kubectl port-forward -n insighthub-prod svc/insighthub-api 18000:8000 --address 127.0.0.1` và `kubectl port-forward -n insighthub-prod svc/insighthub-web 13000:3000 --address 127.0.0.1`. Dùng cổng khác Compose để có thể kiểm tra hai môi trường cùng lúc. Sau đó chạy `python scripts/smoke-k8s-local.py --api-url http://127.0.0.1:18000 --web-url http://127.0.0.1:13000 --poll-timeout 30`. Smoke yêu cầu `/healthz`, `/readyz`, web health trả 200; upload trả đúng 202 trong ≤1 giây; poll đúng ID tới `ready` và `chunk_count>0` trong ≤30 giây; `/chat` trả 200 có answer/sources/contexts; `/metrics` có sample số hữu hạn. Đây là fixture pipeline local, chưa chứng minh provider thật hoặc HTTPS/EKS.

Khi local cluster có `kube-prometheus-stack` với release `kube-prom-stack`, `values-local.yaml` bật `ServiceMonitor` cho `svc/insighthub-api` trên cổng `http`, đường dẫn `/metrics`. Kiểm tra `kubectl get servicemonitor insighthub-api -n insighthub-prod`, rồi xem target `serviceMonitor/insighthub-prod/insighthub-api/0` trong Prometheus. Truy vấn `up{namespace="insighthub-prod",service="insighthub-api"}` phải trả `1`; `insighthub_http_requests_total` phải có series sau khi API nhận request. Chart mặc định tắt `ServiceMonitor` để các môi trường chưa cài Prometheus Operator vẫn triển khai được; đổi `monitoring.serviceMonitor.additionalLabels.release` nếu release monitoring có tên khác.

### Day 4: năm nguồn metric trên kind

`values-local.yaml` bật năm ServiceMonitor trong namespace `insighthub-prod`. Prometheus Operator ở `monitoring` chọn chúng qua nhãn `release: kube-prom-stack`; mỗi ServiceMonitor chọn **Service metadata labels** và tên Service port, không chọn Pod trực tiếp. Các metrics endpoint chỉ nằm trong ClusterIP Service.

| Thành phần | Service/port | Nguồn metric | PromQL kiểm tra sau khi scrape |
| --- | --- | --- | --- |
| Web | `insighthub-web/http` | Node `/metrics`, `prom-client` pin trong lockfile | `insighthub_web_nodejs_eventloop_lag_seconds{service="insighthub-web"}` |
| API | `insighthub-api/http` | FastAPI `/metrics` hiện có | `insighthub_documents_total{service="insighthub-api"}` |
| Worker | `insighthub-worker/metrics` | ARQ metrics server, port 9101 | `insighthub_worker_ready{service="insighthub-worker"}` |
| PostgreSQL | `insighthub-postgres-exporter/metrics` | `postgres_exporter` 9187, dùng Secret hiện có qua file | `pg_up{service="insighthub-postgres-exporter"}` |
| Redis | `insighthub-redis-exporter/metrics` | `redis_exporter` 9121, dùng `REDIS_PASSWORD` từ Secret hiện có | `redis_up{service="insighthub-redis-exporter"}` |

Exporter image được pin theo tag và digest trong `values.yaml`. Exporter chạy ở Deployment riêng, không thay đổi PostgreSQL/Redis StatefulSet hoặc PVC. Redis exporter không bật thu key/value hay client list. Trong Prometheus, cần kiểm tra `/api/v1/targets` có đúng năm job `serviceMonitor/insighthub-prod/insighthub-*/0`, tất cả `health: up` và `lastError` rỗng; `up` một mình không chứng minh exporter đã kết nối database/cache, nên kiểm tra thêm `pg_up=1`, `redis_up=1` và sample riêng của web/API/worker.

Trước khi áp dụng chart, chạy `helm lint helm/insighthub -f helm/insighthub/values-local.yaml` và `helm template insighthub helm/insighthub -n insighthub-prod -f helm/insighthub/values-local.yaml` để review selector, port, Secret reference và image. Khi nâng cấp release Day 3 đã có, dùng `helm upgrade --reset-then-reuse-values` kèm `-f helm/insighthub/values-local.yaml` và các image tag app đã nạp vào kind: cờ này giữ values release cũ và thêm default mới của chart (gồm image exporter). Sau khi có approval triển khai riêng, kiểm tra `kubectl get servicemonitor -n insighthub-prod` và Prometheus API/PromQL; lưu bằng chứng đã lược secret. `values-eks.yaml` chưa bật monitoring Day 4: exporter cho RDS/ElastiCache cần địa chỉ TLS và credential giám sát riêng trước lượt AWS.

### Day 4: dashboard RED/USE

`values-local.yaml` bật ConfigMap `insighthub-day4-dashboard` có nhãn `grafana_dashboard: "1"`. Grafana sidecar của kube-prometheus-stack local đọc ConfigMap ở mọi namespace và provision dashboard UID `insighthub-day4`, datasource UID `prometheus`. Dashboard có 12 panel: API request rate, 5xx %, mean HTTP duration, ARQ queue entries, LLM tokens, HTTP p95, estimated LLM cost, CPU %, memory %, CPU throttling %, container restarts và deployment generation. Bốn panel resource lấy từ cAdvisor/kube-state-metrics; các panel ứng dụng lấy từ ServiceMonitor đã có. Truy vấn 5xx trả 0 chỉ khi đã có mẫu tổng request.

API đo thời gian HTTP bằng histogram theo method, route template và status. Worker đọc `ZCARD` của ARQ queue 5 giây/lần và xuất `insighthub_worker_queue_entries`; đây là số entry trong sorted set, gồm queued, deferred và in-progress, không phải số job chỉ đang chờ. Cần kiểm tra `insighthub_worker_queue_probe_success=1` cùng panel queue. Metric chỉ chứa nhãn có cardinality giới hạn; không chứa câu hỏi, context hoặc nội dung tài liệu.

Token do provider báo dùng `insighthub_llm_tokens_total`; khi thiếu usage, `insighthub_llm_estimated_tokens_total` là ước lượng từ số từ của input/output và được vẽ thành series riêng. `insighthub_llm_estimated_cost_usd_total` là chi phí **ước tính**, không phải hóa đơn. Fixture tạo sample chi phí provider bằng 0 sau chat thật. Với provider thật, phải cấu hình cả `LLM_INPUT_USD_PER_MILLION_TOKENS` và `LLM_OUTPUT_USD_PER_MILLION_TOKENS` theo model/giá đang áp dụng; nếu chưa có giá, cost panel để trống. Khi usage không đủ hai chiều, cost được đánh dấu `usage_source="estimated"`.

Trước khi apply, tạo lại JSON và review diff cùng rendered ConfigMap:

```sh
python scripts/build-day4-dashboard.py
helm lint helm/insighthub -f helm/insighthub/values-local.yaml
helm template insighthub helm/insighthub -n insighthub-prod -f helm/insighthub/values-local.yaml > /tmp/insighthub-day4-rendered.yaml
```

Sau approval riêng cho kind, nâng cấp chart cùng tag image API/worker vừa build và nạp vào kind, giữ Secret/PVC hiện có. Kiểm tra dashboard tại `http://127.0.0.1:13001/d/insighthub-day4` sau `kubectl -n monitoring port-forward svc/kube-prom-stack-grafana 13001:80 --address 127.0.0.1`. Gửi upload/chat thật, đợi ít nhất hai scrape, rồi kiểm tra các truy vấn trong dashboard và chụp toàn bộ 12 panel. Panel cost 0 trong fixture là chi phí provider 0 sau chat thật.

Deploy annotations lấy timestamp của Helm release thực tế từ `helm history insighthub -n insighthub-prod -o json`, rồi gọi Grafana Annotations API bằng `python scripts/annotate-day4-deploy.py --grafana-url http://127.0.0.1:13001 --revision <revision> --time <RFC3339 timestamp>`. Script đọc `GRAFANA_API_TOKEN` hoặc `GRAFANA_USER`/`GRAFANA_PASSWORD` từ environment, không nhận credential qua CLI và chỉ in ID/time của annotation. Không chạy script trước khi dashboard được provision và được duyệt ghi lên kind. Dashboard bật annotation layer `Deploys` để marker xuất hiện trên đồ thị; chọn time range bao gồm timestamp release khi chụp ảnh.

### Day 4: recording rules và anomaly alerts

`values-local.yaml` bật `PrometheusRule` tên `insighthub-day4-anomaly` trong `insighthub-prod`, gắn `release: kube-prom-stack` theo `ruleSelector` của Prometheus Operator local. Chart mặc định tắt rules; đổi `monitoring.rules.additionalLabels` khi Prometheus chọn nhãn khác. File `files/day4-anomaly-rules.yaml` là nguồn chung cho Helm và `promtool`; không sửa riêng rendered manifest. Rule gộp theo `namespace`, không mang nhãn route, document, provider hoặc user vào output.

| Tín hiệu | Recording rule hiện tại | Band và alert | Điều kiện bổ sung |
| --- | --- | --- | --- |
| LLM p95 | `insighthub:llm_latency_p95_seconds:current` từ `insighthub_llm_call_latency_seconds_bucket` | `band_lower`, `band_upper`; `InsightHubLLMLatencyAnomaly` | p95 > 0.5 giây; ít nhất 5 calls/5 phút |
| ARQ entries | `insighthub:queue_entries:current` từ `insighthub_worker_queue_entries` | `band_lower`, `band_upper`; `InsightHubQueueDepthAnomaly` | depth ≥ 3; `insighthub_worker_queue_probe_success=1` |
| HTTP 5xx % | `insighthub:http_5xx_percent:current` từ `insighthub_http_requests_total` | `band_lower`, `band_upper`; `InsightHubHTTP5xxAnomaly` | tỷ lệ > 2%; ít nhất 20 requests/5 phút, bỏ `/metrics` |

Mỗi tín hiệu có thêm recording rule `baseline_ready`. Band dùng trung bình ± 3 độ lệch chuẩn của các giá trị hiện tại trong 1 giờ, bỏ 5 phút mới nhất; độ rộng tối thiểu lần lượt là 0.25 giây, 2 entries và 1 điểm phần trăm. Cận dưới không nhỏ hơn 0. `baseline_ready=1` cần ít nhất 55 mẫu hợp lệ trong cửa sổ 1 giờ và có mẫu cũ ít nhất 65 phút; do đó cần tối thiểu 1 giờ lịch sử trước khi có alert. Mỗi alert cần vượt cận trên liên tục 5 phút. Khi thiếu baseline, thiếu metric, không có traffic hoặc queue probe thất bại, alert liên quan không fire. Một số ít lượt gọi LLM rải rác có thể chưa tạo đủ 55 mẫu p95; cần workload thật đủ đều trong hơn 1 giờ để xác nhận alert runtime. Queue depth là `ZCARD` của ARQ sorted set, bao gồm job queued, deferred và in-progress.

Kiểm tra tĩnh trong WSL tại repo root sau khi kích hoạt `.venv`:

```sh
docker run --rm -v "$(pwd)/helm/insighthub/files:/rules:ro" --entrypoint promtool prom/prometheus:v3.14.0 check rules /rules/day4-anomaly-rules.yaml
docker run --rm -v "$(pwd)/helm/insighthub/files:/rules:ro" --entrypoint promtool prom/prometheus:v3.14.0 test rules /rules/day4-anomaly-rules.test.yaml
helm lint helm/insighthub -f helm/insighthub/values-local.yaml
helm template insighthub helm/insighthub -n insighthub-prod -f helm/insighthub/values-local.yaml > /tmp/insighthub-day4-rules-rendered.yaml
```

Sau khi được duyệt áp dụng lên kind, kiểm tra `kubectl get prometheusrule insighthub-day4-anomaly -n insighthub-prod`, Prometheus `/api/v1/rules` (rule group có `health: ok`) và truy vấn các rule `*:current`, `*:baseline_ready`, `*:band_upper`, `*:band_lower`. Dùng `kubectl -n monitoring port-forward svc/kube-prom-stack-kube-prome-prometheus 19090:9090 --address 127.0.0.1` để truy vấn `http://127.0.0.1:19090/api/v1/query`; đối chiếu source metric và `baseline_ready=1` trước khi mong đợi alert. `promtool test rules` chỉ kiểm chứng chuỗi mô phỏng; không chứng minh alert đã fire trên Prometheus thật hoặc đã gửi notification. Không cấu hình Alertmanager/Slack hoặc tạo incident trong bước này.

### Day 4: Alertmanager route tới Slack

`values-local.yaml` bật `AlertmanagerConfig` tên `insighthub-day4-slack` trong `insighthub-prod`. Route chỉ khớp ba alert `InsightHubLLMLatencyAnomaly`, `InsightHubQueueDepthAnomaly` và `InsightHubHTTP5xxAnomaly`; Prometheus Operator mặc định thêm matcher `namespace=insighthub-prod` cho resource này. Receiver `slack-alerts` đọc key `api_url` từ Secret `insighthub-slack-webhook` cùng namespace và gửi cả thông báo resolved. Title/text nêu tên alert, namespace, summary, description và thời điểm bắt đầu/kết thúc để không chỉ hiển thị link nội bộ. Không tạo silence cho ba incident fixture; driver kiểm tra Alertmanager không có active silence trước khi chạy. Webhook phải được tạo ngoài chart và không được ghi vào values, manifest, evidence hoặc Git. Incoming Webhook của Slack App phải được gắn sẵn với `#alerts`; trường `channel` không đổi được kênh đích đó.

Trước khi áp dụng, kiểm tra Secret chỉ bằng metadata (`kubectl --context kind-insighthub -n insighthub-prod describe secret insighthub-slack-webhook`) và render cấu hình bằng `helm template insighthub helm/insighthub -n insighthub-prod -f helm/insighthub/values-local.yaml --show-only templates/alertmanagerconfig-day4.yaml`. Review diff và manifest, rồi xin approval riêng cho thay đổi cluster. Sau khi triển khai, kiểm tra `kubectl --context kind-insighthub -n insighthub-prod get alertmanagerconfig insighthub-day4-slack` và đối chiếu một alert `firing` từ Prometheus qua Alertmanager tới tin trong Slack `#alerts` bằng tên alert và timestamp. Gửi trực tiếp vào webhook không chứng minh đường alert end-to-end. Chart mặc định và `values-eks.yaml` vẫn tắt route này; EKS cần Secret và kiểm tra riêng trước khi bật.

## Chuyển sang EKS

`values-eks.yaml` tắt PostgreSQL và Redis trong chart, dùng RDS/ElastiCache qua `DATABASE_URL`/`REDIS_URL` ở Secret ngoài chart, và tham chiếu ServiceAccount `insighthub` do Terraform/IRSA tạo. Cần cấu hình image registry/digest, provider thật, TLS và cơ chế đồng bộ Secret từ Secrets Manager trước khi deploy. HTTPS ingress và smoke trên URL thật nằm ở bước AWS riêng. Không đưa credential vào values, log hoặc evidence.

`helm uninstall` sẽ xóa PVC do chart tạo; chỉ thực hiện sau khi đã review dữ liệu và backup cần giữ. Không dùng thao tác xóa để làm test xanh.
