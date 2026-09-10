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

## Prompt 2 - Refactor async ingestion với Redis/ARQ

**Host**: ChatGPT-Codex
**Version / Model / Auth mode**: Codex desktop / GPT-5.6 Sol / OAuth
**Context / Evidence**: `api/app/routers/documents.py`; `api/app/services/ingestion.py`; `api/app/core/{config,db,errors,index}.py`; `api/app/services/{embeddings,llm}.py`; `api/tests/`; `docker-compose.yml`; `api/Dockerfile`; `api/requirements.in`; `ingestion-worker/README.md`; `docs/lab-guides/Day1-AI-Coding-Agents.md`; `Running-Project-Specification-Student.md`; `scripts/VERIFICATION_CONTRACT.md`; `scripts/verify.py`.
**Time**: 2026-09-10 (Asia/Saigon)

**Prompt**:

## 1. Mục tiêu (Goal)

Refactor luồng ingestion hiện tại từ xử lý đồng bộ sang bất đồng bộ bằng Redis và ARQ:

`web → API → enqueue → Redis → ingestion-worker → chunk/embed/store → PostgreSQL`

API chỉ tiếp nhận và xác thực upload, tạo document ở trạng thái `pending`, enqueue job rồi trả HTTP 202 ngay. `ingestion-worker` chạy độc lập để thực hiện extract, chunk, embed, store và cập nhật document thành `ready` hoặc `failed`.

Sau refactor, Docker Compose phải có đủ 5 service bắt buộc: `web`, `api`, `postgres`, `redis`, `ingestion-worker`. `ollama` vẫn là profile tùy chọn và không được tính thay Redis hoặc worker.

## 2. Ràng buộc (Constraints - PHẢI TUÂN THỦ)

- KHÔNG thay đổi schema hiện tại trong `infra/db/init.sql`.
- KHÔNG tạo migration giả hoặc xóa database volume để né vấn đề tương thích.
- PHẢI dùng Redis queue với thư viện ARQ; API và worker phải dùng cùng một `REDIS_URL`.
- PHẢI đổi contract upload có chủ đích từ HTTP 201 đồng bộ sang HTTP 202 bất đồng bộ theo specification.
- Giữ nguyên request upload multipart, các response field đang có nếu còn phù hợp và error contract công khai. Response 202 phải chứa document ID cùng trạng thái chưa hoàn tất như `pending` hoặc `queued`; không được báo `ready` trước khi worker xử lý xong.
- KHÔNG thay đổi contract của `GET /documents`, `DELETE /documents/{document_id}`, `POST /chat`, `/healthz`, `/readyz` và `/metrics`, trừ phần tối thiểu cần thiết đã được specification yêu cầu.
- KHÔNG chuyển retrieval hoặc LLM generation sang worker; worker chỉ phụ trách ingestion.
- Tái sử dụng các bảo đảm hiện có trong `process_document()`: kiểm tra content hash và pipeline identity, row locking, atomic chunk replacement, embedding validation và trạng thái lỗi.
- Retry cùng document ID, filename, content và pipeline KHÔNG được tạo chunk trùng.
- Failure đến muộn KHÔNG được ghi đè một lần retry đã thành công.
- Retry phải có giới hạn tối đa 3 lần với exponential backoff. Phân biệt lỗi có thể retry và lỗi input vĩnh viễn; tài liệu không hợp lệ không được retry vô hạn.
- Không pad/truncate embedding; vector phải finite, đúng count, dimension và embedding identity.
- Không fallback âm thầm từ real provider sang fixture.
- Không log secret, credential, authorization header, raw provider error/body hoặc nội dung tài liệu riêng tư.
- Không hardcode secret; cấu hình Redis và worker phải lấy từ environment variables.
- Duy trì Python type hints và style đang có trong codebase.
- Repo hiện chưa có cấu hình Ruff/Mypy; KHÔNG tự tuyên bố các lệnh lint này đã tồn tại hoặc pass. Nếu đề xuất bổ sung tooling, phải tách rõ khỏi refactor bắt buộc và chờ duyệt.
- KHÔNG xóa, bỏ qua hoặc làm yếu assertions/tests để đạt kết quả xanh.
- Chỉ sửa các file thực sự cần cho async ingestion: API enqueue/config/dependencies, `ingestion-worker/`, Docker Compose, tests và tài liệu Day 1 liên quan. Không refactor lan sang module không liên quan.

## 3. Tiêu chí thành công (Acceptance Criteria)

- `docker compose config --services` thể hiện đủ 5 service bắt buộc: `web`, `api`, `postgres`, `redis`, `ingestion-worker`.
- `docker compose up --build -d --wait` khởi động thành công các service bắt buộc.
- `ingestion-worker/` có implementation thực tế, tối thiểu gồm:
  - `Dockerfile`
  - `requirements.in` và/hoặc `requirements.txt` phù hợp convention khóa dependency của repo
  - ARQ worker entry point và job handler
- `POST /documents`:
  - giữ nguyên multipart upload;
  - xác thực extension, filename, kích thước và nội dung rỗng;
  - tạo document `pending`;
  - enqueue thành công;
  - trả HTTP 202 trong dưới 1 giây với fixture workload;
  - không gọi `ingest_document_sync()` trong request path.
- Worker dequeue job rồi chạy extract/chunk/embed/store, sau đó document chuyển từ `pending` sang `ready` trong dưới 30 giây với fixture workload.
- Khi xử lý thất bại, document chuyển sang `failed`, `chunk_count = 0`, không còn partial chunks và chỉ lộ error code/message an toàn.
- Retry tối đa 3 lần với exponential backoff; retry cùng payload không tạo duplicate chunks.
- `POST /chat` vẫn trả HTTP 200, answer không rỗng và sources đúng sau khi document đã `ready`.
- Cập nhật test sync 201 thành async 202; bổ sung test có tên rõ ràng cho:
  - `test_async_upload`
  - `test_worker_ingests`
  - `test_retry_idempotent`
  - enqueue failure
  - invalid document không retry
  - worker failure cập nhật trạng thái an toàn
  - chat regression
- Các test provider, vector validation, index identity, atomicity và error contract hiện có vẫn phải pass.
- Chạy và báo cáo kết quả thực tế của:
  - `make test-backend`
  - `make test-verifiers`
  - `bash scripts/verify-day-1.sh` với evidence/tham số cần thiết
  - `npm --prefix web run typecheck`
- Không được báo “PASS” cho lệnh chưa chạy hoặc phần chỉ được verifier kiểm tra cấu trúc.

## 4. Ví dụ pattern tham chiếu (Reference)

Đọc và tuân theo các pattern thực tế sau trước khi đề xuất thay đổi:

- `api/app/routers/documents.py`: upload contract hiện tại, validation và nơi đang gọi ingestion đồng bộ.
- `api/app/services/ingestion.py`: `process_document()`, idempotency, row lock, atomic write và failure handling cần được bảo toàn.
- `api/app/core/config.py`: pattern cấu hình bằng Pydantic Settings và environment variables.
- `api/app/core/db.py`: synchronous psycopg pool và lifecycle.
- `api/app/core/errors.py`: public error code/message cố định, không lộ raw exception.
- `api/app/core/index.py`: schema validation và embedding identity.
- `api/app/services/embeddings.py`: provider contract và vector validation.
- `api/app/services/llm.py`: cách tách service/provider logic và xử lý lỗi có kiểm soát; chỉ tham khảo style, không chuyển LLM sang worker.
- `api/tests/test_integration.py` và các unit tests trong `api/tests/`: behavioral contract cần giữ hoặc cập nhật có chủ đích từ 201 sang 202.
- `docker-compose.yml`: service, environment, healthcheck, dependency và resource-limit pattern.
- `api/Dockerfile` và `api/requirements.in`: Python 3.12, non-root runtime và dependency convention.
- `ingestion-worker/README.md`: worker contract bắt buộc của Day 1.
- `docs/lab-guides/Day1-AI-Coding-Agents.md`: acceptance cho async ingestion.
- `Running-Project-Specification-Student.md`, mục Day 1: nguồn yêu cầu chính thức.
- `scripts/VERIFICATION_CONTRACT.md` và `scripts/verify.py`: evidence và verifier contract; không sửa verifier để né failure.

## 5. Quy trình thực hiện (Process / Output Expected)

1. Quét các file tham chiếu và mô tả chính xác:
   - call flow đồng bộ hiện tại;
   - module boundary;
   - database invariants;
   - API/test contract bị ảnh hưởng;
   - các dependency và configuration còn thiếu.

2. Trình bày PLAN trước khi sửa, bao gồm:
   - danh sách file dự kiến tạo/sửa;
   - queue payload và job identity;
   - lifecycle của document;
   - chiến lược enqueue failure;
   - retry/backoff và phân loại lỗi;
   - cách API và worker chia sẻ ingestion code;
   - healthcheck/readiness của Redis và worker;
   - test plan;
   - rủi ro về payload size, duplicate delivery, worker crash và graceful shutdown.

3. ĐỢI TÔI DUYỆT PLAN. Không sửa file, cài dependency, chạy formatter hoặc thay đổi container trước khi được duyệt.

4. Sau khi PLAN được duyệt:
   - triển khai theo từng thay đổi nhỏ;
   - giữ diff tối thiểu;
   - không sửa file ngoài danh sách đã duyệt nếu chưa giải thích lý do;
   - không xóa thay đổi có sẵn của người dùng.

5. Sau triển khai:
   - kiểm tra `git diff` và giải thích từng file;
   - chạy các test/typecheck/verifier phù hợp;
   - thực hiện manual verification: upload → 202 → poll `GET /documents` → `ready` → chat;
   - báo cáo riêng từng lệnh với trạng thái PASS, FAIL hoặc NOT RUN;
   - nếu FAIL, cung cấp nguyên nhân và lệnh tái hiện, không che lỗi hoặc sửa test để né lỗi;
   - liệt kê assumptions, rủi ro còn lại và các phần chưa kiểm chứng.

Output ở bước PLAN phải kết thúc bằng câu hỏi xin phê duyệt rõ ràng và chưa chứa bất kỳ thay đổi file nào.

**Why it worked**:

- Constraint-first prompt giữ refactor trong đúng phạm vi API, Redis/ARQ worker, Compose, tests và tài liệu Day 1.
- Yêu cầu trình bày PLAN trước tạo gate để review queue payload, lifecycle, retry và failure handling trước khi sửa code.
- Các pattern tham chiếu trong ingestion, config, DB, errors, embeddings và LLM giúp giữ nguyên style và các invariant sẵn có.

**What I changed**:

- Reviewed và approved PLAN với phản hồi `ok triển khai đi`.
- Đổi upload từ sync HTTP 201 sang enqueue async HTTP 202; thêm Redis queue và ARQ ingestion worker độc lập.
- Giữ `process_document()` làm shared pipeline, thêm retry tối đa ba lần với exponential backoff và không retry lỗi input vĩnh viễn.
- Thêm đủ năm Compose service, dependency locks, tests async/retry/idempotency và tài liệu Day 1 liên quan.
- Manual verified upload dưới một giây → `pending` → `ready` → chat HTTP 200; backend suite tương đương Make target đạt 54/54 và unit suite đạt 41/41.
- Không báo PASS cho `make test-verifiers`, host `npm typecheck` hoặc `verify-day-1.sh` vì các lệnh này gặp giới hạn tooling/quyền trên host Windows.
