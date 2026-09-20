# Day 1 AI Prompts

## Prompt 1 - Refactor ingestion async

**Host**: ChatGPT-Codex  
**Version / Model / Auth mode**: GPT-5.6 Terra  
**Context / Evidence**: `AGENTS.md`, `Running-Project-Specification-Student.md`, `docs/lab-guides/Day1-AI-Coding-Agents.md`, source files, diff, and test logs.  
**Time**: 2026-09-20 10:36:46 +07:00

**Prompt**:

## 1. Mục tiêu (Goal)

Refactor InsideHub từ ingression đồng bộ sang sử lý nền để có 5 service: web → api → Redis queue → ingestion-worker → PostgreSQL/pgvector

## 2. Ràng buộc (Constraints - PHẢI TUÂN THỦ)

- Không đổi schema của database
- Không đổi request/response của các api đã có
- Dùng Redis queue để xử lý bất đồng bộ
- Không hardcode secret, lưu secret qua env var
- Code style: ruff format + type hints + mypy strict

## 3. Tiêu chí thành công (Acceptance Criteria)

- Docker compose up chạy đủ 5 service
- Upload api trả 202 dưới 1s, worker sử lý nền
- Worker dequeue → chunk + embed + store → status "ready"
- Các test cũ pass (`pytest -xvs`)

## 4. Ví dụ pattern tham chiếu (Reference)

## 5. Quy trình thực hiện (Process / Output Expected)

- Trình bày KẾ HOẠCH (PLAN) từng bước trước.
- ĐỢI TÔI DUYỆT PLAN rồi mới tiến hành sửa file.
- Sau khi chạy, báo cáo kết quả và các thay đổi.

**Why it worked**:

- Prompt đặt mục tiêu, ràng buộc và tiêu chí thành công trước khi triển khai.
- Yêu cầu trình bày PLAN và chờ duyệt tạo điểm kiểm soát để review.
- Các ràng buộc bảo toàn schema, contract API và secret giới hạn phạm vi thay đổi.

**What I changed**:

- Reviewed PLAN trước khi sửa file.
- User approved PLAN trước khi triển khai.
- Đối chiếu diff và thực hiện các kiểm tra phù hợp sau thay đổi.

## Prompt 2 - Update AGENTS.md

**Host**: ChatGPT-Codex
**Version / Model / Auth mode**: GPT-5.6 Terra
**Context / Evidence**: `AGENTS.md`, `api/app/services/queue.py`, `ingestion-worker/worker.py`, `api/app/routers/documents.py`, `docker-compose.yml`, diff, and the six-section/60-line validation.
**Time**: 2026-09-20 11:08:36 +07:00

**Prompt**:

## 1. Mục tiêu (Goal)

Cập nhật AGENTS.md theo các thay đổi mới nhất của project

## 2. Ràng buộc (Constraints - PHẢI TUÂN THỦ)

- Chỉ thay đổi file AGENTS.md, không thay đổi các file khác

## 3. Tiêu chí thành công (Acceptance Criteria)

- AGENTS.md được cập nhật đúng theo trạng thái mới nhất của project, không có các thông tin lỗi thời

## 4. Ví dụ pattern tham chiếu (Reference)

## 5. Quy trình thực hiện (Process / Output Expected)

- Plan trình bày các thông tin sẽ cập nhật
- Chỉ thực hiện thay đổi khi tôi APPROVE plan

**Why it worked**:

- Prompt giới hạn thay đổi trong `AGENTS.md`, bảo toàn các file runtime.
- Yêu cầu PLAN và APPROVE tạo điểm kiểm soát trước khi sửa context dự án.
- Tiêu chí thành công tập trung vào việc loại bỏ mô tả sync/3-service đã lỗi thời.

**What I changed**:

- Đối chiếu `AGENTS.md` với queue adapter, worker, router và Docker Compose.
- Trình bày PLAN, sau đó chỉ sửa `AGENTS.md` khi user APPROVE.
- Kiểm tra file giữ đúng 6 section, 60 dòng và diff không có lỗi whitespace.

## Prompt 3 - Controlled ingestion retry

**Host**: ChatGPT-Codex
**Version / Model / Auth mode**: GPT-5.6 Terra
**Context / Evidence**: `AGENTS.md`, `api/app/services/ingestion.py`, `ingestion-worker/worker.py`, `api/tests/test_integration.py`, diff, `make test-backend` (51 tests pass), and Compose startup with 5 services.
**Time**: 2026-09-20 15:19:10 +07:00

**Prompt**:

## 1. Mục tiêu (Goal)

Hoàn thiện retry tự động cho ingestion-worker khi embedding provider lỗi tạm thời.

Worker retry tối đa 3 lần với exponential backoff. Document giữ `pending` khi còn lượt retry; thành `ready` nếu thành công, hoặc `failed` khi hết lượt.

## 2. Ràng buộc (Constraints - PHẢI TUÂN THỦ)

- Không đổi schema DB, API hoặc thêm state ngoài `pending|ready|failed`.
- Không thêm endpoint retry; API chỉ enqueue và trả `202`.
- Chỉ retry `ProviderError`; không retry lỗi file, conflict, schema hoặc document đã xóa.
- Không retry quá 3 lần, không tạo chunks trùng hoặc dữ liệu partial.
- Giữ transaction, row lock và idempotency hiện có trong `process_document`.
- Log JSON có `event`, `document_id`, `status`, `attempt`, `timestamp`; không log secret hay nội dung tài liệu.
- Không xóa hoặc giảm assertion test.

## 3. Tiêu chí thành công (Acceptance Criteria)

- Lỗi provider lần đầu, thành công lần sau: document `pending` rồi `ready`, chunks không trùng.
- Lỗi provider cả 3 lần: document `failed`, `chunk_count = 0`, không còn chunks partial.
- Lỗi không retryable không được schedule lại.
- Có test cho retry thành công, retry hết lượt và lỗi không retryable.
- `make test-backend` pass.

## 4. Ví dụ pattern tham chiếu (Reference)

- `api/app/services/ingestion.py`
- `ingestion-worker/worker.py`
- `api/tests/test_integration.py`
- `AGENTS.md`

## 5. Quy trình thực hiện (Process / Output Expected)

- Đọc các file tham chiếu và trình bày PLAN theo từng file.
- ĐỢI TÔI APPROVE PLAN rồi mới sửa file.
- Sau khi hoàn tất, chạy test, kiểm tra diff và báo cáo thay đổi cùng kết quả.

**Why it worked**:

- Prompt xác định rõ lỗi được retry và giới hạn ba attempt.
- Giữ state machine `pending|ready|failed`, schema và API không đổi.
- Yêu cầu PLAN, test và diff giúp kiểm soát thay đổi trong pipeline nhạy cảm.

**What I changed**:

- Điều chỉnh pipeline để `ProviderError` còn lượt retry giữ document `pending` và xóa dữ liệu partial.
- Worker log `ingestion_retry_scheduled`; chỉ ghi `failed` khi hết lượt retry.
- Thêm test cho retryable và non-retryable failure; `make test-backend` pass 51 tests và Compose chạy đủ 5 service.
