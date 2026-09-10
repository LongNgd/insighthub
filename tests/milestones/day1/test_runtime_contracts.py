"""Day 1 validation and regression scenarios required by the verifier."""

import json

from runtime_helpers import request, upload, wait_ready


def test_duplicate_or_invalid():
    status, before = request("/documents")
    assert status == 200

    status, error, _ = upload(filename="unsupported.exe")
    assert status == 400
    assert error == {"detail": "Chỉ chấp nhận: .txt, .md, .pdf"}

    status, after = request("/documents")
    assert status == 200
    assert {document["id"] for document in after} == {
        document["id"] for document in before
    }


def test_empty_input():
    status, before = request("/documents")
    assert status == 200

    status, error, _ = upload(content=b"")
    assert status == 422
    assert error["code"] == "invalid_document"
    assert error["detail"] == "Tài liệu trống, không hợp lệ hoặc không có nội dung văn bản."

    status, after = request("/documents")
    assert status == 200
    assert {document["id"] for document in after} == {
        document["id"] for document in before
    }


def test_refactor_regression():
    status, health = request("/healthz")
    assert status == 200
    assert health["status"] == "ok"

    status, readiness = request("/readyz")
    assert status == 200
    assert readiness["status"] == "ready"

    status, document, _ = upload(
        b"InsightHub keeps retrieval and chat in the API after async ingestion."
    )
    assert status == 202
    ready = wait_ready(document["id"])
    assert ready["chunk_count"] > 0

    status, chat = request(
        "/chat",
        json.dumps({"question": "Where do retrieval and chat remain?"}).encode(),
        "application/json",
    )
    assert status == 200
    assert chat["answer"].strip()
    assert chat["sources"]
