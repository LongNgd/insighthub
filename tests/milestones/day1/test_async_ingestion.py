"""Asynchronous ingestion scenarios required by the Day 1 verifier."""

import json
import time

from runtime_helpers import request, upload, wait_ready


def test_async_upload():
    status, document, elapsed = upload()
    assert status == 202
    assert document["status"] == "pending"
    assert document["chunk_count"] == 0
    assert elapsed < 1


def test_worker_ingests():
    status, document, _ = upload()
    assert status == 202
    ready = wait_ready(document["id"])
    assert ready["chunk_count"] > 0
    status, chat = request(
        "/chat",
        json.dumps({"question": "InsightHub dùng queue nào?"}).encode(),
        "application/json",
    )
    assert status == 200
    assert chat["answer"].strip()
    assert chat["sources"]


def test_retry_idempotent():
    status, document, _ = upload(b"Idempotent retry keeps one logical chunk set.")
    assert status == 202
    first = wait_ready(document["id"])
    time.sleep(1)
    _, documents = request("/documents")
    current = next(item for item in documents if item["id"] == document["id"])
    assert current["chunk_count"] == first["chunk_count"]
