# Day 2 — Debug session: Sample target không được Prometheus scrape

## Mục tiêu

Thực hành điều tra một target Prometheus bị lỗi bằng Docker MCP và Prometheus MCP, xác định nguyên nhân gốc, khắc phục, rồi xác minh hệ thống phục hồi.

## Phạm vi

- Service được kiểm tra: `sample-target` trong `observability/compose.yaml`
- Công cụ sử dụng:
  - Docker MCP: kiểm tra trạng thái container và đọc logs
  - Prometheus MCP: kiểm tra scrape target và chạy query `up`
- Không thay đổi cấu hình Prometheus hoặc sample target trong lúc debug.

## Triệu chứng

Prometheus hiển thị target `sample-target` ở trạng thái `DOWN`.

Query Prometheus:

```promql
up{job="sample-target"}
```

Kết quả quan sát được:

```text
0
```

## Điều tra

### 1. Kiểm tra scrape status bằng Prometheus MCP

Prometheus MCP cho thấy:

```text
job: sample-target
health: down
endpoint: http://sample-target:9100/metrics
```

Điều này xác nhận Prometheus không thu thập được metrics từ sample target.

### 2. Kiểm tra container bằng Docker MCP

Docker MCP được dùng để liệt kê container và kiểm tra trạng thái `sample-target`.

Kết quả:

```text
container: sample-target
status: exited / stopped
```

### 3. Đọc logs bằng Docker MCP

Docker MCP đọc logs của `sample-target`.

Kết quả:

```text
Không có lỗi ứng dụng cần xử lý; container đã bị dừng trong kịch bản debug.
```

## RCA — Root Cause Analysis

Nguyên nhân gốc là container `sample-target` không chạy. Vì endpoint
`http://sample-target:9100/metrics` không còn sẵn sàng, Prometheus không thể
scrape metrics và ghi nhận target ở trạng thái `DOWN`.

Đây là lỗi availability của container, không phải lỗi cấu hình scrape của
Prometheus.

## Khắc phục

Khởi động lại `sample-target`:

```bash
docker compose -f observability/compose.yaml start sample-target
```

## Xác minh sau khắc phục

Docker MCP xác nhận `sample-target` đang chạy.

Prometheus MCP chạy lại query:

```promql
up{job="sample-target"}
```

Kết quả:

```text
1
```

Prometheus Targets hiển thị cả hai target ở trạng thái `UP`:

```text
prometheus: UP
sample-target: UP
```

## Kết luận

Docker MCP giúp xác định container `sample-target` đã dừng; Prometheus MCP xác
nhận ảnh hưởng trực tiếp đến scrape status. Sau khi khởi động lại container,
metrics được thu thập trở lại và target chuyển về `UP`.
