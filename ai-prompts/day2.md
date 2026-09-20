# Day 2 AI Prompts

## Prompt 1 - Prometheus và sample target bằng Docker

**Host**: ChatGPT-Codex  
**Version / Model / Auth mode**: GPT-5.6 Terra  
**Time**: 20/09/2026 23:08:27 +07  
**Context / Evidence**: [Compose](../observability/compose.yaml),
[Prometheus config](../observability/prometheus.yml),
[lab README](../observability/README.md). Xác minh bằng Docker Compose,
`promtool`, Prometheus targets API và PromQL.

**Prompt**:

```text
## 1. Mục tiêu (Goal)

Tạo Prometheus chạy bằng Docker để thực hành theo dõi metrics.

Có một sample target để Prometheus thu thập dữ liệu mẫu.

## 2. Ràng buộc (Constraints - PHẢI TUÂN THỦ)

- Prometheus và sample target chạy bằng Docker.
- Cấu hình đơn giản, dễ hiểu.
- Tất cả file liên quan phải nằm trong thư mục `observability`.
- Không được tạo, sửa hoặc xóa bất kỳ file nào bên ngoài thư mục `observability`.
- Chỉ làm Prometheus và sample target.
- Không triển khai thêm các thành phần observability khác.

## 3. Tiêu chí thành công (Acceptance Criteria)

- Prometheus chạy ổn định và truy cập được.
- Sample target chạy và cung cấp metrics.
- Prometheus thu thập được metrics từ sample target.
- Prometheus hiển thị cả chính nó và sample target ở trạng thái UP.

## 4. Ví dụ pattern tham chiếu (Reference)

Mô hình mong muốn:

Prometheus:

- tự theo dõi chính nó
- thu thập metrics từ sample target

Toàn bộ cấu hình nằm trong thư mục:observability

Ưu tiên cách triển khai tối giản.

## 5. Quy trình thực hiện (Process / Output Expected)

1. Kiểm tra cấu trúc hiện tại.
2. Đưa ra plan gồm các thay đổi dự kiến.
3. Dừng lại để tôi kiểm tra và xác nhận plan.
4. Sau khi được xác nhận, thực hiện đúng plan.
5. Kiểm tra kết quả và báo cáo lại.
```

**Why it worked**:

- Phạm vi giới hạn rõ trong `observability` và chỉ gồm hai service.
- Tiêu chí thành công có thể kiểm chứng trực tiếp bằng healthcheck, targets API và PromQL.
- Bước duyệt plan giữ quyết định triển khai ở người dùng trước khi thay đổi file và khởi chạy container.

**What I changed / Review**:

- Người dùng đã duyệt plan gồm `observability/compose.yaml`,
  `observability/prometheus.yml` và cập nhật hướng dẫn trong `observability/README.md`.
- Chấp nhận Compose riêng với Prometheus `v3.14.0` và Node Exporter
  `v1.12.1`, scrape mỗi 5 giây, chỉ bind cổng vào localhost.
- Chấp nhận `tmpfs` cho dữ liệu lab; metrics mất khi container dừng hoặc tạo lại.
- Không thêm Grafana, Alertmanager hoặc thành phần observability khác.
