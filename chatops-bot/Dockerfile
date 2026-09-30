# Build from the project root:
# docker build -f chatops-bot/Dockerfile -t insighthub-chatops:local .

FROM node:24.16.0-bookworm-slim AS mcp-deps
WORKDIR /opt/mcp
COPY tools/mcp/package.json tools/mcp/package-lock.json ./
# The ChatOps bridge uses the pinned MCP client currently declared as a dev
# dependency, so CI must retain it until the package split is revisited.
RUN npm ci --ignore-scripts

FROM python:3.12.14-slim@sha256:78387bc3881b8273120a12ebe6c1ab22b018ccc2c9adf565ae1ac9b536e184ea AS python-deps
WORKDIR /tmp/requirements
COPY chatops-bot/requirements.txt ./
RUN pip install --no-cache-dir --require-hashes -r requirements.txt

FROM python:3.12.14-slim@sha256:78387bc3881b8273120a12ebe6c1ab22b018ccc2c9adf565ae1ac9b536e184ea AS runtime
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /app

RUN groupadd --system --gid 1001 botuser \
    && useradd --system --uid 1001 --gid botuser botuser

COPY --from=python-deps /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=python-deps /usr/local/bin /usr/local/bin
COPY --from=mcp-deps /usr/local/bin/node /usr/local/bin/node
COPY --from=mcp-deps /opt/mcp/node_modules ./tools/mcp/node_modules
COPY --chown=botuser:botuser chatops-bot/app ./app
COPY --chown=botuser:botuser tools/mcp/src ./tools/mcp/src

USER botuser
EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/healthz')" || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
