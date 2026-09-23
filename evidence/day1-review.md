# Day 1 Async Ingestion Review

## Change reviewed

Document upload moved from synchronous ingestion with HTTP 201 to an asynchronous
HTTP 202 flow. The API validates the upload, creates a `pending` document, and
enqueues `process_document_job` through Redis/ARQ. The ingestion worker runs the
existing atomic chunk, embed, validate, and store pipeline, then records `ready`
or `failed`.

## Risks and controls

The main risk is partial chunks or duplicate chunks when a provider fails and the
worker retries. `process_document` retains its row lock and savepoint pattern,
deletes partial chunks on failure, and is idempotent for the same document,
payload, and pipeline. Retryable provider failures remain `pending` until ARQ
retries; non-retryable failures and the final provider attempt become `failed`.

## Validation performed

`make test-backend` passed 51 tests, including async upload, retryable provider
failure, non-retryable document failure, idempotency, atomic cleanup, and chat
regression coverage. Docker Compose started `web`, `api`, `redis`,
`ingestion-worker`, and `postgres`; the worker connected to Redis. A fresh upload
was polled through `GET /documents` and reached `ready` with one chunk and no
error code.
