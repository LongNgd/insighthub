# Prometheus lab — chuẩn bị Day 2

Compose riêng gồm hai container:

- Prometheus `v3.14.0`: tự scrape và scrape sample target mỗi 5 giây.
- Node Exporter `v1.12.1`: sample target cung cấp CPU/memory/time và metrics của exporter.

Sample target không mount filesystem máy chủ. Metrics phản ánh môi trường Linux
Docker đang thấy, không phải bộ giám sát đầy đủ máy Windows.
Prometheus dùng tmpfs: dữ liệu metrics mất khi container dừng hoặc được tạo lại.

## Chạy và kiểm tra

Từ thư mục gốc dự án trong WSL:

```bash
source .venv/bin/activate
docker compose -f observability/compose.yaml config --quiet
docker compose -f observability/compose.yaml up -d --wait
docker compose -f observability/compose.yaml exec -T prometheus promtool check config /etc/prometheus/prometheus.yml
docker compose -f observability/compose.yaml ps
```

- Prometheus: <http://localhost:9090>
- Targets: <http://localhost:9090/targets> — cả `prometheus` và `sample-target` phải UP.
- Metrics mẫu: <http://localhost:9100/metrics>

Chờ khoảng 15 giây sau khi khởi động để scrape hoàn tất. Trong trang Query,
chạy `up`: hai series đều phải bằng `1`. Thử thêm `node_exporter_build_info`
hoặc `node_time_seconds` để xem metrics đã thu thập từ sample target.

```bash
curl --fail http://localhost:9090/-/ready
curl --fail http://localhost:9100/metrics
curl --fail 'http://localhost:9090/api/v1/query?query=up'
docker compose -f observability/compose.yaml logs --tail=50
```

Dừng lab:

```bash
docker compose -f observability/compose.yaml stop
```

Chạy lại bằng `up -d --wait` ở trên. Hai cổng chỉ bind localhost.

## Observability và MLOps - bắt buộc Day 4

ServiceMonitor/exporters cho đủ5 thành phần, Grafana9+ panels,3 anomaly và3 incident/RCA, Slack alert, MLOps overview notes4 blocks/quiz. Queue/worker Day 1 và deployment Day 3 phải có thật. [Spec mục 8](../Running-Project-Specification-Student.md).

Dùng telemetry local cho baseline; không giữ AWS chạy liên tục. Alloy/OTel có thể cải tiến collector, không bỏ các nhiệm vụ gốc.
