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
