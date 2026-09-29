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
