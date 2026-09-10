"""Runtime Day 1 contract tests; the verifier supplies loopback API coordinates."""

import json
import os
import time
import urllib.request
import uuid


API_URL = os.environ.get("INSIGHTHUB_API_URL", "http://localhost:8000")


def _request(path: str, data: bytes | None = None, content_type: str | None = None):
    headers = {"Content-Type": content_type} if content_type else {}
    request = urllib.request.Request(API_URL + path, data=data, headers=headers)
    with urllib.request.urlopen(request, timeout=10) as response:
        return response.status, json.loads(response.read())


def _upload(content: bytes = b"InsightHub async ingestion uses Redis and ARQ."):
    boundary = "InsightHub" + uuid.uuid4().hex
    filename = "day1-" + uuid.uuid4().hex + ".md"
    body = (
        f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{filename}"\r\n'
        "Content-Type: text/markdown\r\n\r\n"
    ).encode() + content + f"\r\n--{boundary}--\r\n".encode()
    started = time.monotonic()
    status, document = _request(
        "/documents", body, "multipart/form-data; boundary=" + boundary
    )
    return status, document, time.monotonic() - started


def _wait_ready(document_id: int):
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        status, documents = _request("/documents")
        assert status == 200
        matches = [item for item in documents if item.get("id") == document_id]
        if matches and matches[0]["status"] == "ready":
            return matches[0]
        time.sleep(0.25)
    raise AssertionError("document did not become ready within 30 seconds")


def test_async_upload():
    status, document, elapsed = _upload()
    assert status == 202
    assert document["status"] == "pending"
    assert document["chunk_count"] == 0
    assert elapsed < 1


def test_worker_ingests():
    status, document, _ = _upload()
    assert status == 202
    ready = _wait_ready(document["id"])
    assert ready["chunk_count"] > 0
    status, chat = _request(
        "/chat",
        json.dumps({"question": "InsightHub dùng queue nào?"}).encode(),
        "application/json",
    )
    assert status == 200
    assert chat["answer"].strip()
    assert chat["sources"]


def test_retry_idempotent():
    status, document, _ = _upload(b"Idempotent retry keeps one logical chunk set.")
    assert status == 202
    first = _wait_ready(document["id"])
    time.sleep(1)
    _, documents = _request("/documents")
    current = next(item for item in documents if item["id"] == document["id"])
    assert current["chunk_count"] == first["chunk_count"]
