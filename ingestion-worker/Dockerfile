FROM python:3.12.14-slim@sha256:78387bc3881b8273120a12ebe6c1ab22b018ccc2c9adf565ae1ac9b536e184ea AS base
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /app

FROM base AS deps
COPY api/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir --require-hashes -r /tmp/requirements.txt \
    && pip install --no-cache-dir arq==0.26.3 redis[hiredis]==5.3.1 PyJWT==2.14.0 hiredis==3.3.0

FROM base AS runtime
RUN groupadd --system --gid 1001 appuser \
    && useradd --system --uid 1001 --gid appuser appuser
COPY --from=deps /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=deps /usr/local/bin /usr/local/bin
COPY --chown=appuser:appuser api/app ./app
COPY --chown=appuser:appuser ingestion-worker/worker.py ./worker.py
USER appuser
CMD ["arq", "worker.WorkerSettings", "--custom-log-dict", "worker.SAFE_LOG_CONFIG"]
