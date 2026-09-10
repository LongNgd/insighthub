"""Shared HTTP helpers for the Day 1 runtime contract tests."""

import json
import os
import time
import urllib.error
import urllib.request
import uuid
from typing import Any


API_URL = os.environ.get("INSIGHTHUB_API_URL", "http://localhost:8000")


def request(
    path: str, data: bytes | None = None, content_type: str | None = None
) -> tuple[int, Any]:
    headers = {"Content-Type": content_type} if content_type else {}
    http_request = urllib.request.Request(API_URL + path, data=data, headers=headers)
    try:
        with urllib.request.urlopen(http_request, timeout=10) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as exc:
        with exc:
            return exc.code, json.loads(exc.read())


def upload(
    content: bytes = b"InsightHub async ingestion uses Redis and ARQ.",
    filename: str | None = None,
) -> tuple[int, Any, float]:
    boundary = "InsightHub" + uuid.uuid4().hex
    upload_filename = filename or "day1-" + uuid.uuid4().hex + ".md"
    body = (
        f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{upload_filename}"\r\n'
        "Content-Type: text/markdown\r\n\r\n"
    ).encode() + content + f"\r\n--{boundary}--\r\n".encode()
    started = time.monotonic()
    status, document = request(
        "/documents", body, "multipart/form-data; boundary=" + boundary
    )
    return status, document, time.monotonic() - started


def wait_ready(document_id: int) -> dict[str, Any]:
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        status, documents = request("/documents")
        assert status == 200
        matches = [item for item in documents if item.get("id") == document_id]
        if matches and matches[0]["status"] == "ready":
            return matches[0]
        time.sleep(0.25)
    raise AssertionError("document did not become ready within 30 seconds")
