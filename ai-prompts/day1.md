# Day 1 AI Prompts

## Prompt 1 - Refactor AGENTS.md project context

**Host**: ChatGPT-Codex
**Version / Model / Auth mode**: Codex desktop / GPT-5.6 Sol / OAuth
**Context / Evidence**: `AGENTS.md`; `README.md`; `GETTING_STARTED.md`; `Makefile`; `docker-compose.yml`; `infra/db/init.sql`; `api/app/`; `api/tests/`; `web/package.json`; `tools/mcp/package.json`; `.github/workflows/starter.yml`; `git diff -- AGENTS.md`; kết quả kiểm tra được ghi lại bên dưới
**Time**: 2026-09-10 09:09:29 +07:00 (Asia/Saigon)

**Prompt**:

### 1. Mục tiêu (Goal)

Quét (scan) toàn bộ codebase hiện tại và refactor file `AGENTS.md`, thay thế 100% các mục `TODO` bằng dữ liệu và thông tin kỹ thuật thật của project.

### 2. Ràng buộc (Constraints - PHẢI TUÂN THỦ)

- Trích xuất thông tin THỰC TẾ từ các file hiện có; KHÔNG tự bịa lệnh hay thư viện.
- Giữ file `AGENTS.md` cô đọng ≤ 200 dòng để tránh tràn ngữ cảnh và bị trôi thông tin (lost in the middle).
- Bắt buộc duy trì section "Constraints" chứa các quy tắc KHÔNG ĐƯỢC LÀM (vd: không hardcode secret, không bypass migration DB, không git push force).
- KHÔNG tự ý chỉnh sửa bất kỳ file code nào khác trong dự án ngoại trừ `AGENTS.md`.

### 3. Tiêu chí thành công (Acceptance Criteria)

- Xóa sạch 100% chữ `TODO` trong file `AGENTS.md`.
- Các câu lệnh build, test, lint, migration ghi trong `AGENTS.md` phải chính xác và chạy được thực tế trong dự án.
- Cấu trúc chuẩn hóa đủ 6 phần: Architecture, Conventions, Commands, Constraints, Domain Knowledge, References.

### 4. Quy trình thực hiện (Process)

- BƯỚC 1: Đọc codebase và trình bày KẾ HOẠCH (PLAN) liệt kê các thông tin thật bạn tìm được cho từng mục.
- BƯỚC 2: Đợi tôi duyệt PLAN. Sau khi tôi đồng ý mới tiến hành ghi nội dung hoàn chỉnh vào file `AGENTS.md`.

Phê duyệt sau PLAN:

> Được, refactor đi, không xóa các phần đã có trong AGENTS.md, chỉ thay phần TODO.

**Why it worked**:

- Constraint-first prompt giúp agent tập trung vào duy nhất `AGENTS.md` và không chỉnh sửa application code.
- "Trình bày PLAN trước" tạo gate để người dùng review phạm vi trước khi agent ghi file.
- Yêu cầu trích xuất thông tin thật buộc agent đối chiếu source, manifests, Compose, database schema, tests và documentation thay vì tự đặt command hoặc dependency.
- Chỉ thị sau PLAN làm rõ rằng phải giữ nguyên nội dung và section hiện hữu, chỉ thay sáu dòng `TODO`.
- Các kiểm tra cuối xác nhận không còn `TODO`, đủ sáu section, dưới 200 dòng và diff chỉ chạm `AGENTS.md`.

**What I changed**:

- Đã review PLAN và phê duyệt với một ràng buộc bổ sung: giữ nguyên toàn bộ nội dung hiện có và chỉ thay các mục `TODO`.
- Đã thay sáu mục `TODO` bằng thông tin đã được kiểm chứng về architecture, conventions, commands, constraints, domain rules và references.
- Đã giữ nguyên tiêu đề `Domain` thay vì đổi thành `Domain Knowledge`, tuân theo ràng buộc trong bước phê duyệt.
- Đã xác minh `rg -n 'TODO' AGENTS.md` không trả về kết quả nào.
- Đã xác minh `AGENTS.md` vẫn có 45 dòng nội dung và đủ sáu section.
- Đã xác minh `git diff --check -- AGENTS.md` không báo lỗi whitespace và tại thời điểm đó `git status --short` chỉ liệt kê `AGENTS.md`.
- Không triển khai ingestion-worker, Redis/ARQ, retry logic hoặc bất kỳ thay đổi nào đối với application code trong prompt này.

Prompt 2 và Prompt 3 sẽ được bổ sung sau khi các AI-assisted workflow tương ứng thực sự được thực hiện.
