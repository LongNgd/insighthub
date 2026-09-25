# Day 3 AI Prompts

## Prompt 1 - Viết SPEC triển khai Day 3

**Host**: ChatGPT-Codex

**Model / Auth mode**: GPT-6 Terra

**Ngày**: 23/09/2026 (+07:00)

**Context / Evidence**: [SPEC Day 3](../infra/SPEC.md), [Running Project Specification](../Running-Project-Specification-Student.md), [Day 3 lab guide](../docs/lab-guides/Day3-AI-IaC-Pipeline.md), [Local/AWS cost guide](../docs/Guide_Local_AWS_Cost_DO2603.md), [Verification contract](../scripts/VERIFICATION_CONTRACT.md).

**Prompt gốc**:

```text
## 1. Mục tiêu (Goal)

Viết SPEC cho Day 3: đưa InsightHub từ local lên Kubernetes/EKS bằng Terraform, Helm và GitHub Actions.

## 2. Ràng buộc (Constraints)

- Chỉ viết SPEC, KHÔNG sửa code, KHÔNG tạo AWS resource.
- Bám theo:
  - `Running-Project-Specification-Student.md`
  - `docs/lab-guides/Day3-AI-IaC-Pipeline.md`
  - `docs/Guide_Local_AWS_Cost_DO2603.md`
  - `scripts/VERIFICATION_CONTRACT.md`
- Kiến trúc gồm: `web`, `api`, `ingestion-worker`, Redis, PostgreSQL/pgvector.
- AWS dùng EKS, RDS, ElastiCache, IRSA, Secrets Manager.
- GitHub Actions dùng OIDC, không dùng access key dài hạn.
- Có HTTPS, cost estimate và teardown.

## 3. Acceptance Criteria

SPEC phải nêu rõ cách kiểm tra:

- Terraform fmt/validate PASS.
- tflint, Checkov, Conftest PASS.
- CI: `fmt → lint → security-scan → policy-check → plan → cost-estimate → apply`.
- Apply có manual approval.
- Workload Ready trên Kubernetes.
- `/healthz` → `200`.
- Upload → `202`.
- Document `ready` trong ≤ 30 giây.
- `/chat` → `200`.
- Có evidence deployment, CI, smoke test, cost và teardown.

## 4. Output Expected

- Đọc tài liệu trong repo trước.
- Viết SPEC bằng Markdown, ngắn gọn, dễ verify.
- Mỗi yêu cầu ghi: phải làm gì, cách kiểm tra, evidence cần lưu.
- Cuối cùng liệt kê các file dự kiến cần tạo/sửa.
```

**Vì sao prompt hiệu quả**:

- Khoanh phạm vi vào tài liệu SPEC và nêu rõ bốn nguồn cần đối chiếu.
- Gắn từng tiêu chí với cách kiểm tra và evidence, giúp review được trước khi triển khai.
- Giữ rõ ranh giới giữa kiểm tra local, verifier một phần và xác minh AWS/HTTPS thật.

**Quyết định / Review**:

- Chấp nhận SPEC sau khi đối chiếu nguồn và diff; theo yêu cầu tiếp theo của người dùng, chuyển file đến `infra/SPEC.md` và sửa liên kết tương đối.
- SPEC ghi rõ kiến trúc, Terraform/S3 locking, policy gate, GitHub Actions/OIDC, Helm/HTTPS, smoke, cost, teardown và danh sách file dự kiến. Đây là yêu cầu triển khai, chưa phải evidence rằng hạ tầng đã chạy.
- Kiểm tra sau thay đổi: `git diff --no-index --check /dev/null infra/SPEC.md` không báo lỗi whitespace; `python -m unittest discover -s tests -p test_verify.py -q` đạt 57 tests. Phạm vi thay đổi đến lúc ghi log: `infra/SPEC.md` và prompt log này; không sửa runtime code, không tạo AWS resource.
- Rủi ro còn lại: chưa có Terraform/Helm/workflow, CI run, smoke HTTPS, chi phí thực tế hoặc evidence teardown. Ghi các prompt và quyết định tiếp theo khi công việc đó thực sự diễn ra.

## Prompt 2 - Terraform skeleton cho hạ tầng

**Host**: ChatGPT-Codex

**Ngày**: 23/09/2026 (+07:00)

**Context / Evidence**: [SPEC Day 3](../infra/SPEC.md), [Terraform root](../infra/main.tf), [hướng dẫn triển khai](../infra/README.md), diff và kết quả fmt/validate/tflint.

**Prompt gốc**:

```text
## 1. Mục tiêu (Goal)

Dựa trên SPEC Day 3 đã duyệt, lập PLAN để tạo Terraform skeleton cho hạ tầng InsightHub.

## 2. Ràng buộc (Constraints - PHẢI TUÂN THỦ)

- CHƯA sửa file ở bước này.
- CHƯA tạo AWS resource.
- Bám đúng SPEC Day 3 đã duyệt.
- Terraform phải dùng version đã pin và hỗ trợ S3 backend với `use_lockfile`.
- Cấu trúc ban đầu tối thiểu gồm:\
  `main.tf`, `variables.tf`, `outputs.tf`, `providers.tf`, `versions.tf`.
- Không hardcode secret hoặc thông tin nhạy cảm.

## 3. Tiêu chí thành công (Acceptance Criteria)

PLAN phải nêu rõ:

- Các file cần tạo/sửa.
- Mục đích của từng file.
- Thứ tự triển khai Terraform.
- Các resource/module chính dự kiến dùng.
- Cách verify bằng `terraform fmt`, `validate`, `tflint`, Checkov.

## 4. Ví dụ pattern tham chiếu (Reference)

- Tham khảo SPEC Day 3 đã duyệt.
- Ưu tiên cấu trúc Terraform đơn giản, dễ đọc và dễ mở rộng.

## 5. Quy trình thực hiện (Process / Output Expected)

- Đọc SPEC và cấu trúc `infra/` hiện tại.
- Trình bày PLAN từng bước.
- Chỉ ra file nào sẽ tạo hoặc sửa.
- KHÔNG sửa code/file.
- ĐỢI TÔI DUYỆT PLAN rồi mới bắt đầu triển khai.
```

**Phê duyệt và chỉnh sửa của người dùng**: `insighthub-<env>` đổi thành `insighthub-prod`; người dùng duyệt PLAN và yêu cầu triển khai.

**Quyết định / Review**:

- Chấp nhận root Terraform đơn giản với AWS, Kubernetes và TLS provider được pin; S3 backend có `use_lockfile`. EKS/RDS/ElastiCache/IRSA là resource khai báo; VPC/private subnet là đầu vào của lab, không thuộc state này.
- Namespace `insighthub-prod` và ServiceAccount `insighthub` tạo ở giai đoạn hai, sau khi EKS sẵn sàng; không dùng `-target` làm quy trình thường lệ. SPEC được cập nhật theo tên namespace người dùng chọn.
- Token Redis đi qua input `sensitive` và Secrets Manager, không hardcode; token vẫn có mặt trong Terraform state/plan nên phải bảo vệ state và plan. RDS quản lý master password trong Secrets Manager; ứng dụng cần DB user riêng trước khi deploy Helm.
- `terraform fmt -check -recursive`, `terraform validate` và `tflint --recursive` đạt. Đã cài Checkov `3.3.19` vào `.venv`; `pip check` không có dependency hỏng và 57 test verifier đạt.
- `checkov -d infra/ --framework terraform --quiet --compact`: 94 checks đạt, 6 findings, 0 skipped, exit 1; output lưu tại [Checkov report](../evidence/day3-checkov.txt). Đã sửa các finding về EKS logging, mô tả security group, RDS TLS/logging/monitoring, KMS và tag snapshot; số finding giảm từ 19 xuống 6. Sáu ID còn lại và lý do chưa xử lý được ghi trong `infra/README.md`. Gate Checkov đầy đủ chưa đạt; output độc lập không gán severity, nên không tuyên bố đã chứng minh "no HIGH".
- Chưa chạy plan/apply, chưa tạo AWS resource. Các cấu hình logging/monitoring/KMS thêm chi phí và KMS key cần theo dõi trong teardown.
- Các phần Helm, GitHub Actions/OIDC, Conftest, Infracost, HTTPS, smoke và teardown vẫn cần prompt/triển khai/evidence riêng.

## Prompt 3 - PLAN Helm và Kubernetes local

**Host**: ChatGPT-Codex

**Ngày cập nhật log**: 24/09/2026 (+07:00)

**Context / Evidence**: [SPEC Day 3](../infra/SPEC.md), [Running Project Specification](../Running-Project-Specification-Student.md), [Docker Compose](../docker-compose.yml), [Helm chart](../helm/insighthub/Chart.yaml).

**Prompt gốc**:

```text
## 1. Mục tiêu (Goal)

Dựa trên SPEC Day 3 và yêu cầu trong `Running-Project-Specification-Student.md`, lập PLAN để tạo Helm chart và chạy InsightHub đầy đủ trên Kubernetes local trước khi triển khai AWS.

## 2. Ràng buộc (Constraints - PHẢI TUÂN THỦ)

- CHƯA sửa file ở bước này.
- CHƯA tạo AWS resource.
- Bám đúng `infra/SPEC.md` và yêu cầu Day 3.
- Kubernetes local phải chạy đủ 5 thành phần:
  - `web`
  - `api`
  - `ingestion-worker`
  - Redis
  - PostgreSQL + pgvector
- Giữ nguyên kiến trúc async và API contract hiện tại.
- Không hardcode secret.
- Helm chart phải thiết kế để sau này chuyển sang EKS, khi đó Redis và PostgreSQL local sẽ được thay bằng ElastiCache và RDS.

## 3. Tiêu chí thành công (Acceptance Criteria)

PLAN phải nêu rõ cách verify:

- Helm chart tại `helm/insighthub/`.
- Namespace `insighthub-`prod.
- Cả 5 thành phần chạy thành công.
- `web`, `api`, `ingestion-worker` Ready.
- Redis và PostgreSQL/pgvector kết nối được.
- `/healthz` trả `200`.
- Upload `/documents` trả `202`.
- Document chuyển sang `ready` trong ≤ 30 giây.
- `/chat` trả `200` và có answer.
- Có cách kiểm tra pod, service, logs và rollout.

## 4. Ví dụ pattern tham chiếu (Reference)

- `Running-Project-Specification-Student.md` mục Day 3.
- `infra/SPEC.md`.
- `docker-compose.yml` hiện tại để map image, port, env, volume và dependency sang Kubernetes.

## 5. Quy trình thực hiện (Process / Output Expected)

- Đọc cấu trúc repo, SPEC và Docker Compose hiện tại.
- Đề xuất cấu trúc `helm/insighthub/`.
- Liệt kê resource Kubernetes cần tạo cho cả 5 thành phần.
- Nêu rõ Deployment/StatefulSet, Service, ConfigMap, Secret, PVC và probes nếu cần.
- Nêu cách build/load image vào cluster local.
- Nêu thứ tự deploy và smoke test.
- Nêu rõ file nào sẽ tạo hoặc sửa.
- KHÔNG sửa file.
- ĐỢI TÔI DUYỆT PLAN rồi mới triển khai.
```

**Quyết định / Review**:

- Người dùng đã duyệt PLAN Helm/Kubernetes local trong hội thoại. Prompt gốc được lưu nguyên văn; dòng namespace có lỗi dấu backtick và được hiểu là `insighthub-prod` theo SPEC và chart.
- Việc ghi lại prompt này chỉ cập nhật prompt log; không phải bằng chứng rằng các workload Ready hoặc smoke test đã PASS.
