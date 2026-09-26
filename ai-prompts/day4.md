# Day 4 AI Prompts

## Prompt 1 - ServiceMonitor/exporter cho năm thành phần

**Host**: ChatGPT-Codex

**Model**: GPT-6 Sol

**Ngày ghi log**: 27/09/2026 (+07:00)

**Context / Evidence**: [AGENTS.md](../AGENTS.md), [Running Project Specification](../Running-Project-Specification-Student.md), [Day 4 lab guide](../docs/lab-guides/Day4-AIOps-Observability.md), [Helm chart README](../helm/insighthub/README.md), [manifest kind](../evidence/day4-kind-monitoring-preview.yaml), [evidence runtime](../evidence/day4-kind-monitoring.md).

**Prompt gốc**:

```text
## 1. Mục tiêu (Goal)

Hoàn thành riêng yêu cầu ServiceMonitor/exporter của lab Day 4: Prometheus thu metric của đủ năm thành phần InsightHub (`web`, `api`, `ingestion-worker`, PostgreSQL/pgvector, Redis) và xác nhận mọi scrape target dự kiến đều UP.

## 2. Ràng buộc (Constraints - PHẢI TUÂN THỦ)

- Đọc `Running-Project-Specification-Student.md` mục 8, `docs/lab-guides/Day4-AIOps-Observability.md`, `AGENTS.md` và Helm chart hiện có trước khi đề xuất thay đổi.
- Tận dụng `/metrics` và ServiceMonitor hiện có của API. Chọn metric endpoint hoặc exporter phù hợp cho bốn thành phần còn lại; pin version image/dependency, không dùng `latest`.
- ServiceMonitor phải khớp namespace, label selector, tên Service port và label của Prometheus Operator thực tế. Không coi việc tạo ServiceMonitor là bằng chứng đã scrape thành công.
- Không đổi API contract, DB schema hay luồng ingestion. Không đưa secret hoặc nội dung tài liệu vào metric, label, log hay evidence; tránh label cardinality cao.
- Ưu tiên kiểm chứng trên kind local. Mọi thay đổi lên cluster/cloud cần trình bày manifest, cluster/context và tác động để tôi duyệt riêng trước khi áp dụng. Không xóa dữ liệu hoặc PVC.
- Chỉ xử lý phạm vi thu metric và xác nhận target UP; không triển khai dashboard, alert hay RCA trong yêu cầu này.

## 3. Tiêu chí thành công (Acceptance Criteria)

- Có cấu hình thu metric rõ ràng cho từng thành phần: `web`, `api`, `ingestion-worker`, PostgreSQL/pgvector và Redis.
- `helm lint` và `helm template` PASS; các ServiceMonitor/exporter render đúng selector, port và endpoint.
- Trên môi trường được phép triển khai, `kubectl get servicemonitor` cho thấy cấu hình đã áp dụng.
- Prometheus `/api/v1/targets` cho thấy **đủ các target dự kiến** và tất cả có `health: up`. Truy vấn PromQL chứng minh có sample metric của từng thành phần; không dùng riêng `up` hoặc metric pod chung để thay cho bằng chứng metric ứng dụng/exporter.
- Báo cáo bảng gồm: thành phần, nguồn metric, ServiceMonitor/scrape job, metric kiểm tra, trạng thái target và bằng chứng lệnh/output. Nếu chưa có cluster hoặc Prometheus khả dụng, ghi rõ phần nào mới được kiểm chứng tĩnh và phần nào còn chờ kiểm chứng runtime; không tuyên bố PASS giả.

## 4. Ví dụ pattern tham chiếu (Reference)

- `helm/insighthub/templates/servicemonitor-api.yaml`
- `helm/insighthub/values.yaml` và `values-local.yaml`
- `helm/insighthub/README.md`
- `api/app/core/metrics.py`
- Yêu cầu Day 4 MH1–MH2 trong `Running-Project-Specification-Student.md`

## 5. Quy trình thực hiện (Process / Output Expected)

- Trước tiên, kiểm tra cấu hình hiện tại và trình bày KẾ HOẠCH theo từng thành phần: metric lấy từ đâu, cần sửa file nào, cách Prometheus discovery và cách xác minh.
- **ĐỢI TÔI DUYỆT KẾ HOẠCH rồi mới sửa file.** Xin duyệt riêng trước mọi thao tác làm thay đổi cluster/cloud.
- Sau khi được duyệt, review diff theo từng file, chạy test/Helm checks liên quan và xác minh target bằng Prometheus API cùng PromQL.
- Kết thúc bằng kết quả PASS/FAIL cho từng tiêu chí, lệnh kiểm tra thủ công, bằng chứng thực tế và các giới hạn còn lại.
```

**Vì sao prompt hiệu quả**:

- Phạm vi giới hạn vào năm nguồn metric và xác nhận scrape; từng tiêu chí có thể kiểm tra bằng Helm, Kubernetes và Prometheus.
- Hai điểm duyệt tách biệt cho thay đổi file và mutation cluster giúp review manifest, context và tác động trước khi áp dụng.
- Yêu cầu metric riêng cho từng thành phần ngăn việc xem ServiceMonitor tồn tại hoặc chỉ có `up` là bằng chứng hoàn thành.

**Quyết định / Review**:

- Người dùng duyệt kế hoạch sửa file, sau đó duyệt riêng việc áp dụng lên context `kind-insighthub`, namespace `insighthub-prod`.
- Chấp nhận dùng `/metrics` của API hiện có; bổ sung `/metrics` cho web, HTTP metrics server cho worker và exporter riêng cho PostgreSQL/Redis. Image/dependency được pin; Secret chỉ được tham chiếu, không đưa giá trị vào manifest hoặc evidence.
- `helm lint` và `helm template` cho local/EKS PASS; Helm release `insighthub` revision 13 ở trạng thái `deployed`. `kubectl get servicemonitor` thấy đủ năm ServiceMonitor. Prometheus `/api/v1/targets` có đủ năm target `health: up`; PromQL trả sample metric riêng cho từng thành phần. Lệnh và output đã lược dữ liệu nhạy cảm nằm trong [evidence runtime](../evidence/day4-kind-monitoring.md).
- Giới hạn: kết quả runtime chỉ áp dụng cho kind local. Monitoring Day 4 trên EKS chưa triển khai; metric PostgreSQL xác nhận database đang chứa pgvector, chưa đo riêng trạng thái extension hoặc hiệu năng vector index. Không triển khai dashboard, alert hoặc RCA trong prompt này.
