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
