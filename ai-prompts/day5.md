# Day 5 AI Prompts

## Prompt 1 - Slack HTTP event fail-closed

**Host**: ChatGPT-Codex

**Model**: Codex (GPT-5)

**Ngày ghi log**: 29/09/2026 (+07:00)

**Context / Evidence**: [AGENTS.md](../AGENTS.md), [Day 5 specification](../Running-Project-Specification-Student.md), [verification contract](../scripts/VERIFICATION_CONTRACT.md), [ChatOps scaffold](../chatops-bot/app/main.py), [audit module](../chatops-bot/app/audit.py), [ChatOps tests](../chatops-bot/tests/test_slack_events.py).

**Prompt gốc**:

```text
## 1. Mục tiêu (Goal)

Hoàn thiện lớp nhận Slack HTTP event trong `chatops-bot/` theo hướng fail-closed:

- Đọc raw body và xác thực Slack signature/timestamp trước khi parse JSON, trả URL challenge hoặc ghi log.
- Từ chối request có timestamp quá 5 phút để chống replay.
- Sau khi xác thực mới parse event và lọc self-event của bot, tránh vòng lặp tự trả lời.
- Giữ `/healthz` phản ánh đúng trạng thái adapter đã cấu hình.

## 2. Ràng buộc (Constraints - PHẢI TUÂN THỦ)

- Chỉ sửa trong phạm vi `chatops-bot/**` và test liên quan; không sửa API InsightHub, database schema, Day 1–4, MCP backend hoặc web.
- KHÔNG nhận, parse, log, echo URL challenge, enqueue hay gọi tool trước khi signature và timestamp hợp lệ.
- PHẢI đọc exact raw request body để xác thực Slack `v0` HMAC-SHA256 theo tài liệu Slack; dùng constant-time comparison.
- PHẢI lấy Slack signing secret, bot user ID và mọi cấu hình từ environment variables; không hardcode secret, token, URL hay user ID.
- Request thiếu header, signature sai, timestamp không hợp lệ, hoặc timestamp lệch quá 300 giây phải bị từ chối bằng HTTP 401 với lỗi đã sanitize; không phản chiếu raw input hoặc lỗi crypto.
- Không log raw Slack body, signature, timestamp header, token, document/RAG content hoặc exception thô.
- Chỉ trả URL verification challenge sau khi authentication thành công.
- Self-event chỉ được lọc sau authentication và parse an toàn; event từ `bot_id` hoặc `event.user == configured_bot_user_id` không được đi tiếp vào xử lý câu hỏi.
- Không thêm fallback “development mode” bỏ qua signature; không dùng prompt để thay enforcement.
- Dùng Python type hints đầy đủ, controlled errors, snake_case và dependency pin/hash theo pattern repository.
- Giữ thiết kế tương thích bước kế tiếp: endpoint chỉ authenticate + validate + filter + chuẩn bị ACK; chưa tự gọi LLM/MCP hoặc thực hiện mutation trong request path.
- Không sửa/xóa/skip/xfail test hiện có hoặc nới assertion để làm test xanh.

## 3. Tiêu chí thành công (Acceptance Criteria)

- `POST /slack/events` với signature thiếu/sai trả 401 và không parse/echo/log body.
- Request có signature đúng nhưng timestamp cũ hơn 5 phút, timestamp tương lai bất thường, hoặc timestamp không phải số nguyên trả 401.
- URL challenge có signature và timestamp hợp lệ được trả thành công; challenge không hợp lệ vẫn trả 401.
- Event hợp lệ từ bot/self được ACK thành công nhưng không gọi handler/queue.
- Event hợp lệ từ user được xác thực, parse an toàn và chuyển sang điểm tích hợp xử lý bất đồng bộ đã định nghĩa, nhưng chưa thực thi LLM/MCP trong HTTP request.
- `/healthz` phản ánh adapter đã configured/ready mà không tiết lộ secret.
- Có test độc lập cho: valid signature, invalid signature, expired timestamp, malformed timestamp, challenge trước/sau auth, self-event, user event và đảm bảo log không chứa raw body/secret.
- `pytest chatops-bot/tests/` PASS, không có skip/xfail.
- Không có thay đổi ngoài scope; báo cáo `git diff --check` PASS.

## 4. Ví dụ pattern tham chiếu (Reference)

- Đọc scaffold và fail-closed contract tại `chatops-bot/app/main.py` và `chatops-bot/app/audit.py`.
- Theo Day 5 specification tại `Running-Project-Specification-Student.md` mục 9: raw-body signature/timestamp trước challenge hoặc parse/log, replay window 5 phút, ACK dưới 3 giây và self-event filtering.
- Tham khảo error sanitization/configuration patterns tại `api/app/core/config.py` và `api/app/core/errors.py`, nhưng không sửa các file đó.
- Audit phải tuân thủ `scripts/VERIFICATION_CONTRACT.md`: dữ liệu audit được structured và sanitized, không chứa raw Slack payload hay secret.

## 5. Quy trình thực hiện (Process / Output Expected)

- Trình bày KẾ HOẠCH (PLAN) từng bước trước, bao gồm danh sách file dự kiến sửa/thêm, luồng xác thực và danh sách test.
- ĐỢI TÔI DUYỆT PLAN rồi mới tiến hành sửa file.
- Trước khi sửa, đọc toàn bộ các file reference và test hiện có để không phá contract.
- Sau khi sửa, tự chạy `git diff --check` và `pytest chatops-bot/tests/`.
- Báo cáo: file đã đổi, tóm tắt security flow, kết quả test, các biến môi trường cần cấu hình (chỉ tên biến, không giá trị), và cách verify bằng tay với valid/invalid Slack request.
- Không tạo Slack event thật, không gửi Slack message, không mở ngrok/Ingress và không thực hiện mutation cluster nếu chưa có quyền riêng.
```

**Vì sao prompt hiệu quả**:

- Luồng raw body → replay window → HMAC constant-time → JSON parse đặt rõ thứ tự enforcement, nên URL challenge và event body không thể được xử lý trước authentication.
- Phạm vi giới hạn vào adapter HTTP, đồng thời tách ACK khỏi LLM/MCP và mọi mutation để không biến HTTP request thành đường thực thi tool.
- Acceptance criteria bao phủ cả replay tương lai, self-event, sanitization log và tình trạng adapter, với test độc lập và `git diff --check` làm bằng chứng kiểm tra.

**Quyết định / Review**:

- Người dùng đã duyệt kế hoạch trước khi thay đổi source. Phạm vi thực hiện giữ trong `chatops-bot/` và test ChatOps; không gửi Slack event thật, không mở ngrok/Ingress và không mutation cluster/cloud.
- Chấp nhận `SLACK_SIGNING_SECRET` và `SLACK_BOT_USER_ID` là cấu hình bắt buộc từ environment. Adapter không cấu hình báo `not_ready`; request hợp lệ chỉ chuẩn bị qua async integration seam, chưa enqueue hay gọi LLM/MCP.
- Xác thực dùng exact raw body với Slack `v0` HMAC-SHA256 và `hmac.compare_digest`; timestamp phải là ASCII integer trong cửa sổ ±300 giây. Challenge chỉ được echo sau auth; `bot_id` hoặc configured bot user ID được ACK nhưng không tới seam.
- Đã thêm 14 test cho signature/timestamp/challenge/self-event/user event/health/audit sanitization. `python -m compileall -q chatops-bot/app chatops-bot/tests`, `pytest chatops-bot/tests/` và `git diff --check` đều PASS tại thời điểm review. Không thêm dependency và không có skip/xfail.
- Giới hạn: durable queue/dedup/retry, ba intent, MCP execution, permission/approval và Slack LIVE evidence vẫn là công việc Day 5 tiếp theo; test transport nội bộ không thay cho evidence Slack LIVE.

## Prompt 2 - Durable Slack event queue

**Host**: ChatGPT-Codex

**Model**: Codex (GPT-5)

**Ngày ghi log**: 29/09/2026 (+07:00)

**Context / Evidence**: [AGENTS.md](../AGENTS.md), [Day 5 specification](../Running-Project-Specification-Student.md), [Day 5 lab guide](../docs/lab-guides/Day5-ChatOps-Incident-Response.md), [verification contract](../scripts/VERIFICATION_CONTRACT.md), [Slack transport](../chatops-bot/app/main.py), [queue adapter](../chatops-bot/app/queue.py), [worker](../chatops-bot/app/worker.py), [ChatOps tests](../chatops-bot/tests/).

**Prompt gốc**:

```text
## 1. Mục tiêu (Goal)

Triển khai pipeline xử lý Slack event bất đồng bộ cho `chatops-bot/`:

- Sau khi lớp HTTP đã xác thực Slack signature/timestamp, endpoint phải persist/enqueue event và ACK thành công trong dưới 3 giây.
- Xử lý AI/MCP và gửi Slack reply chỉ diễn ra trong worker durable, không nằm trong HTTP request path.
- Chống xử lý trùng Slack event bằng dedup theo event identity.
- Worker retry lỗi transient có giới hạn, backoff rõ ràng và không gửi reply trùng.

## 2. Ràng buộc (Constraints - PHẢI TUÂN THỦ)

- Chỉ sửa trong phạm vi `chatops-bot/**`, dependency/config liên quan trực tiếp và tests Day 5; không sửa API InsightHub, database schema, web, MCP backend hoặc Day 1–4.
- Coi lớp raw-body Slack signature/timestamp và self-event filter đã hoàn tất: queue chỉ nhận normalized event đã authenticated; không được tạo đường enqueue bypass authentication.
- HTTP handler phải ACK ngay sau khi durable enqueue thành công; không gọi AI, MCP, Slack reply API, `handle_question`, hoặc chờ worker trong request path.
- Dùng Redis + ARQ cho queue durable. Không dùng `BackgroundTasks`, in-memory queue, thread tự tạo, task asyncio không bền vững, hoặc polling tự chế để thay thế queue.
- Đọc Redis URL, queue settings, timeout, retry limit, Slack credential và mọi endpoint từ environment variables qua settings; không hardcode secret, token, URL, timeout hoặc Redis endpoint.
- Dedup phải dựa trên identity Slack ổn định, ưu tiên top-level `event_id` kết hợp workspace/team khi cần. Dedup phải atomic và tồn tại qua restart; duplicate event không được enqueue lại hoặc gửi reply lần hai.
- Xử lý race condition: hai request đồng thời cùng event chỉ được nhận một lần.
- Worker retry chỉ cho lỗi transient đã phân loại; tối đa 3 attempts với exponential backoff có giới hạn. Lỗi validation/permission/dedup/permanent không retry.
- Khi retry hết, ghi trạng thái lỗi đã sanitize và audit; không nuốt exception, không retry vô hạn, không lộ raw provider/MCP/Slack error.
- Một job chỉ được gửi Slack reply sau khi AI/MCP processing thành công. Cần có cơ chế idempotent để retry sau lỗi gửi reply không tạo reply trùng.
- Bounded deadline cho mỗi bước AI, MCP và Slack reply; worker không được treo vô hạn.
- Không nhận tool/action từ prompt tự do: worker chỉ gọi intent router và allowlist/capability server-side đã định nghĩa. Read-only chỉ trong phạm vi RBAC/allowlist hiện có.
- Audit structured JSON cho enqueue, dedup, retry, success/failure và reply decision; ghi UTC timestamp, event/run ID, user, action/tool, decision và sanitized summary. Không log raw Slack body, nội dung tài liệu/RAG, signature, token hay exception thô.
- Dùng type hints đầy đủ, snake_case, controlled errors và dependency versions pinned/hashes theo conventions repository.
- Không sửa/xóa/skip/xfail test hiện có hoặc giảm assertion để làm test xanh.

## 3. Tiêu chí thành công (Acceptance Criteria)

- Với event authenticated hợp lệ, `/slack/events` ACK trong dưới 3 giây sau durable enqueue; HTTP request không gọi AI/MCP/Slack reply.
- Nếu Redis/queue không khả dụng, endpoint trả lỗi sanitized phù hợp và không giả ACK thành công.
- Event đầu tiên được enqueue đúng một lần; gửi lại cùng Slack event, kể cả đồng thời hoặc sau process restart, không tạo job/reply trùng.
- Worker lấy job từ Redis/ARQ, gọi điểm xử lý intent một cách bounded và gửi deferred reply qua Slack adapter.
- Transient failure retry tối đa 3 lần theo exponential backoff; permanent failure không retry; exhausted retry có audit lỗi sanitized.
- Retry của cùng job không tạo duplicate Slack reply.
- Có test cho: ACK/deferred processing, queue unavailable, dedup sequential, dedup concurrent, dedup qua restart/storage, transient retry/backoff, permanent failure, retry exhausted, idempotent reply và audit fields.
- `pytest chatops-bot/tests/` PASS, không skip/xfail.
- `git diff --check` PASS.

## 4. Ví dụ pattern tham chiếu (Reference)

- Tham khảo queue adapter hiện có tại `api/app/services/queue.py` và worker pattern tại `ingestion-worker/worker.py`, nhưng không sửa hay sao chép ingestion pipeline vào ChatOps bot.
- Tham khảo Redis/ARQ configuration hiện có trong `.env.example`, `docker-compose.yml` và `api/app/core/config.py`; thiết kế bot có settings riêng, không hardcode.
- Tham khảo contract Day 5 trong `Running-Project-Specification-Student.md` mục 9 và `docs/lab-guides/Day5-ChatOps-Incident-Response.md`: ACK <3 giây, durable queue, dedup và bounded retry.
- Tham khảo audit contract tại `scripts/VERIFICATION_CONTRACT.md`; fresh test run phải có audit cho decision phù hợp và không chứa dữ liệu nhạy cảm.
- Giữ ranh giới bảo mật từ `chatops-bot/app/main.py`: transport chỉ authenticate/ACK; worker mới xử lý công việc sau đó.

## 5. Quy trình thực hiện (Process / Output Expected)

- Trình bày KẾ HOẠCH (PLAN) từng bước trước, gồm:
  1. các file dự kiến sửa/thêm;
  2. state machine enqueue → dedup → process → reply/retry;
  3. Redis keys/TTL và cách atomic dedup;
  4. phân loại lỗi retryable/non-retryable;
  5. cách bảo đảm không reply trùng;
  6. danh sách test.
- ĐỢI TÔI DUYỆT PLAN rồi mới tiến hành sửa file.
- Trước khi sửa, đọc toàn bộ queue/worker/config/test pattern hiện có và kiểm tra contract hiện tại của Slack adapter.
- Sau khi sửa, chạy `git diff --check` và `pytest chatops-bot/tests/`.
- Báo cáo: file thay đổi, luồng ACK/worker/retry/dedup, tên biến môi trường cần thêm (không nêu giá trị secret), kết quả test, và cách verify thủ công bằng một event hợp lệ gửi hai lần.
- Không gửi Slack message thật, không mở ngrok/Ingress, không mutate Kubernetes/cloud và không dùng token thật nếu chưa có quyền riêng.
```

**Vì sao prompt hiệu quả**:

- Tách rõ HTTP transport khỏi Redis/ARQ worker, nên yêu cầu ACK dưới ba giây không thể bị AI, MCP hoặc Slack reply chặn trên request path.
- Quy định identity, atomic dedup, TTL và retry bounded giúp bao phủ duplicate delivery, race condition và restart mà không dựa vào bộ nhớ tiến trình.
- Phân loại lỗi, idempotent reply, deadline và audit sanitization biến các yêu cầu reliability/security thành các điểm kiểm thử cụ thể.
- Allowlist intent và cấm biến prompt thành tool/action giữ enforcement ở server/worker thay vì dựa vào instruction của người dùng.

**Quyết định / Review**:

- Người dùng đã duyệt kế hoạch trước khi thay đổi source. Phạm vi thực hiện giữ trong `chatops-bot/`, dependency/config trực tiếp và test ChatOps; không gửi Slack event thật, không mở ngrok/Ingress và không mutation cluster/cloud.
- Chấp nhận Redis + ARQ cho queue durable: transport chỉ authenticate → normalize → dedup claim → enqueue → ACK. Queue không khả dụng phải trả lỗi đã sanitize, không trả ACK giả.
- Dedup dùng identity opaque từ workspace/event ID, `SET NX EX` atomic và TTL cấu hình. Khi enqueue thất bại, chỉ claim của request hiện tại được giải phóng; duplicate không tạo job hoặc reply mới.
- Worker chỉ route intent read-only nằm trong allowlist, retry lỗi transient đã phân loại tối đa ba lần với exponential backoff; validation, permission/allowlist và permanent errors không retry. Audit chỉ ghi metadata/sanitized summary.
- Reply giữ trạng thái idempotent bền vững và stable client message identity. Rủi ro còn lại là cần xác nhận Slack LIVE và MCP Day 2 adapters/permissions trong evidence riêng; test double không thay bằng chứng production.

## Prompt 3 - ChatOps read-only MCP intents

**Host**: ChatGPT-Codex

**Model**: Codex (GPT-5)

**Ngày ghi log**: 29/09/2026 (+07:00)

**Context / Evidence**: [AGENTS.md](../AGENTS.md), [Day 5 specification](../Running-Project-Specification-Student.md), [Day 5 lab guide](../docs/lab-guides/Day5-ChatOps-Incident-Response.md), [verification contract](../scripts/VERIFICATION_CONTRACT.md), [documents router](../api/app/routers/documents.py), [custom MCP](../tools/mcp/), [ChatOps queue/worker](../chatops-bot/app/queue.py), [ChatOps worker](../chatops-bot/app/worker.py), [Kubernetes read-only RBAC](../kubernetes/mcp/mcp-readonly.yaml), [ChatOps tests](../chatops-bot/tests/).

**Prompt gốc**:

```text
## 1. Mục tiêu (Goal)

Hoàn thiện ba intent ChatOps thật cho `chatops-bot/`, dùng capability MCP read-only có allowlist và trả triage/context/recommendation an toàn:

1. **Health InsightHub**: kết hợp InsightHub health/readiness và Prometheus context cố định.
2. **Số document ingest hôm nay**: đếm chính xác theo ngày UTC, không truy vấn tự do và không lộ metadata tài liệu.
3. **Pods lỗi**: dùng Kubernetes MCP với quyền read-only/RBAC, liệt kê pod bất thường và trả triage/recommendation, không thực hiện mutation.

Bổ sung capability read-only cố định `insighthub_ingest_count_today_utc` để bot có thể trả lời đúng intent thứ hai.

## 2. Ràng buộc (Constraints - PHẢI TUÂN THỦ)

- Chỉ sửa các file cần thiết trong `chatops-bot/**`, `tools/mcp/**`, `api/app/routers/documents.py`, cấu hình/dependency liên quan và tests. Không sửa database schema, web, ingestion pipeline, Day 3/4 infrastructure hay thay đổi MCP quyền ghi.
- Không thêm endpoint `/upload`, `/status`, truy vấn SQL tự do, PromQL từ model, URL tùy ý, shell command, `kubectl exec`, hoặc bất kỳ tool mutation/delete/scale nào.
- Không thay đổi API contract hiện có. Endpoint mới chỉ được là read-only, response tối thiểu, không chứa filename, document id, document content, user data hoặc lỗi provider thô.
- Bổ sung endpoint fixed-purpose để đếm ingest của **ngày UTC hiện tại**, không nhận ngày, filter hay query từ client/model. Response chỉ chứa:
  - `date_utc`
  - `interval_start_utc`
  - `interval_end_utc`
  - `count`
- Ngày được định nghĩa là `[00:00:00Z, 00:00:00Z ngày kế tiếp)`; dùng thời gian UTC timezone-aware và query có bound rõ ràng. Không đổi schema database.
- Bổ sung MCP tool `insighthub_ingest_count_today_utc` không nhận arguments, chỉ gọi endpoint fixed-purpose nói trên; cập nhật allowlist, manifest, SDK tests và projection an toàn.
- Health intent chỉ được dùng capability cố định:
  - `insighthub_health`;
  - Prometheus summary với các query ID allowlist hiện có như `requests_5m` và `errors_5m`.
  Không cho model gửi PromQL, URL, labels hay time range tùy ý.
- Pods intent phải đi qua Kubernetes MCP read-only với namespace lấy từ cấu hình operator, không từ câu hỏi người dùng. Chỉ cho phép list/get dữ liệu cần cho triage; không watch vô hạn, exec, logs, apply, patch, delete hoặc scale.
- Pod được xem là cần triage khi có trạng thái/condition/reason bất thường đã định nghĩa rõ trong code, ví dụ `Failed`, `CrashLoopBackOff`, `ImagePullBackOff`, `CreateContainerConfigError`, restart bất thường hoặc condition chưa ready. Response phải giới hạn số pod, sanitize field và nêu recommendation; không trả raw Kubernetes object.
- Bot không được thừa kế ngầm kubeconfig hoặc Codex desktop MCP config. MCP transport, namespace, timeouts và credential reference phải là cấu hình runtime riêng của bot qua env/Secret.
- Không gọi tool theo prompt tự do. Intent router phải map ba intent sang capability cố định ở server-side; intent không hỗ trợ phải từ chối/an toàn.
- Mọi MCP call phải có deadline, bounded output, controlled/sanitized error và audit JSON. Không log raw Slack body, secret, kubeconfig, document content, raw MCP/provider error hoặc full pod object.
- Giữ permission boundary: ba intent này là read-only. Recommendation không tự biến thành scale/action; mutation vẫn phải qua approval flow riêng.
- Dùng type hints đầy đủ, Python/TypeScript style theo từng module, dependency pin/hash và không dùng `latest`.
- Không sửa/xóa/skip/xfail test hay giảm assertion để làm test xanh.

## 3. Tiêu chí thành công (Acceptance Criteria)

- Intent health trả lời với API liveness/readiness và Prometheus request/error context từ tool allowlist; Prometheus unavailable phải trả triage đã sanitize, không bịa số liệu.
- Intent ingest hôm nay trả count đúng cho UTC boundary, gồm test tại `00:00:00Z`, trước boundary và sau boundary; không trả document metadata.
- `insighthub_ingest_count_today_utc` không nhận argument, không nhận date/query/URL tùy ý, không đăng ký khi không nằm trong allowlist và bị chặn nếu gọi trực tiếp khi disabled.
- Intent pods lỗi gọi Kubernetes MCP read-only với namespace cấu hình; kết quả chỉ gồm thông tin triage cần thiết, có giới hạn số lượng và recommendation.
- Pod healthy không bị báo sai là lỗi; pod bất thường có reason/restart/condition phù hợp được nêu rõ.
- Kubernetes/Prometheus MCP lỗi hoặc timeout không lộ exception thô, không retry vô hạn và không làm bot gọi fallback quyền cao hơn.
- Intent không hỗ trợ hoặc prompt cố ép tool mutation bị deny; không có tool call tự do.
- Audit có event/run ID, UTC timestamp, user, action/tool, decision và sanitized result summary cho từng MCP call.
- Có tests cho:
  - health healthy/degraded/Prometheus unavailable;
  - ingest count UTC boundary và tool input/allowlist;
  - pods healthy/failing/malformed/oversized response/MCP timeout;
  - namespace không do user control;
  - prompt injection/tool mutation denial;
  - audit sanitization.
- `npm --prefix tools/mcp test`, `pytest chatops-bot/tests/`, các API tests liên quan, và `git diff --check` đều PASS.

## 4. Ví dụ pattern tham chiếu (Reference)

- `tools/mcp/src/core.mjs` và `tools/mcp/src/server.mjs`: capability fixed-route, allowlist hai lớp, timeout, projection và sanitize error.
- `tools/mcp/manifest.json` cùng các test MCP: cập nhật tool contract thay vì tạo một client/tool ad-hoc.
- `api/app/routers/documents.py`: thêm read-only endpoint tối thiểu theo router/config/error pattern hiện có.
- `api/app/routers/health.py` và `api/app/core/metrics.py`: health/readiness và metric contract InsightHub.
- `.codex/config.toml` và `kubernetes/mcp/mcp-readonly.yaml`: Kubernetes MCP/read-only RBAC là reference quyền; bot phải có runtime configuration và identity riêng.
- `Running-Project-Specification-Student.md` mục 9: ba intent, MCP K8s/Prometheus, triage/context, permission enforcement và audit.
- `scripts/VERIFICATION_CONTRACT.md`: audit fields, test observation và nguyên tắc verifier chỉ là partial evidence.

## 5. Quy trình thực hiện (Process / Output Expected)

- Trình bày KẾ HOẠCH (PLAN) trước, nêu rõ:
  1. file dự kiến sửa/thêm;
  2. API contract mới cho count UTC;
  3. MCP manifest/allowlist/tool schema thay đổi;
  4. kiến trúc bot MCP client và cấu hình runtime riêng;
  5. tiêu chí phân loại pod lỗi;
  6. response/triage format và giới hạn output;
  7. test matrix.
- ĐỢI TÔI DUYỆT PLAN rồi mới sửa file.
- Trước khi sửa, đọc toàn bộ implementation và tests hiện có của `tools/mcp`, API documents/health, ChatOps queue/worker và Kubernetes RBAC.
- Sau khi sửa, chạy các test ở Acceptance Criteria và báo cáo output.
- Báo cáo rõ tên các env var/Secret reference cần operator cấu hình, nhưng không in secret hay kubeconfig.
- Cung cấp cách verify thủ công cho ba intent bằng test transport trước; Slack LIVE, ngrok/Ingress, Secret creation hay Kubernetes mutation chỉ thực hiện khi có quyền riêng.
```

**Vì sao prompt hiệu quả**:

- Chuyển ba intent thành capability cố định ở server-side, nên Slack text không thể đưa PromQL, URL, namespace hoặc lệnh mutation vào đường gọi tool.
- Tách aggregate UTC ingest khỏi endpoint metadata, đồng thời yêu cầu half-open interval và projection tối thiểu để bảo vệ dữ liệu tài liệu.
- Buộc pod triage qua MCP read-only/RBAC, output bounded và tiêu chí bất thường xác định rõ; recommendation không có quyền tự động biến thành action.
- Biến các ràng buộc deadline, allowlist, error sanitization và audit thành acceptance tests cụ thể cho cả capability lẫn bot worker.

**Quyết định / Review**:

- Người dùng đã duyệt plan trước khi sửa source. Phạm vi thực hiện giữ trong `api/app/routers/documents.py`, `tools/mcp/**`, `chatops-bot/**`, config/template liên quan và tests; không sửa schema, web, ingestion pipeline, Day 3/4 infrastructure hoặc MCP write permission.
- Chấp nhận endpoint `GET /documents/ingest-count/today-utc` không nhận input, dùng UTC timezone-aware với điều kiện `created_at >= start AND created_at < end`, và chỉ trả bốn field aggregate đã yêu cầu.
- Chấp nhận tool `insighthub_ingest_count_today_utc` schema `{}` với fixed route và hai lớp allowlist. Tool bị disable không được đăng ký và direct call bị từ chối; không có SQL/date/query/URL từ caller.
- Bot dùng MCP JSON-RPC transport riêng qua env/Secret, không đọc `.codex/config.toml` hoặc thừa kế kubeconfig. K8s chỉ gọi `get_pods` với namespace operator-owned; response projection giới hạn pod và chỉ giữ phase/restart/reason an toàn.
- Đã thêm tests cho health healthy/degraded/Prometheus unavailable, UTC boundary, allowlist/input, pod healthy/failing/malformed/oversized/timeout, namespace injection, mutation denial và audit sanitization. `make test-backend` (62 tests), `pytest chatops-bot/tests/` (40 tests), `make test-mcp` (23 tests cùng fixture smoke) và `git diff --check` đều PASS tại thời điểm review.
- Rủi ro còn lại: test transport/fixture không phải Slack LIVE hoặc attestation Kubernetes/Prometheus production. Không gửi Slack message thật, không tạo Secret, không mở ngrok/Ingress và không mutation Kubernetes/cloud.
