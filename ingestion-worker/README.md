# Ingestion worker - bắt buộc Day 1

Học viên tách sync ingestion thành Redis/ARQ + worker độc lập, hoàn thiện 5 thành phần. POST /documents trả 202; GET /documents chọn ID pending->ready/failed; retry/idempotency và dữ liệu atomic; chat không regression.

Worker dùng cùng package ingestion của API và nhận job `ingest_document` có ID
`ingestion:<document_id>`. Lỗi input vĩnh viễn không retry; lỗi provider/service
được retry tối đa ba lần với backoff 1s, 2s. API và worker đọc cùng
`REDIS_URL`; nội dung tài liệu chỉ nằm trong payload job và không được ghi log.

Đây là nền cho queue/backlog/anomaly Day 4 và ingestion intent Day 5, không phải extension tùy chọn. [Spec mục 5](../Running-Project-Specification-Student.md). Lệnh verify-day-1 mặc định kiểm tra async worker.
