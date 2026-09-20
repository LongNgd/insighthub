"""Live Day 1 contract checks for the running Compose stack."""

import json
import os
from pathlib import Path
import subprocess
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen
import uuid

import pytest


API_URL = os.environ.get("INSIGHTHUB_API_URL", "http://localhost:8000").rstrip("/")
REPO_ROOT = Path(os.environ["INSIGHTHUB_REPO_ROOT"])


def request_json(path: str, *, method: str = "GET", body: bytes | None = None, headers: dict[str, str] | None = None) -> tuple[int, object]:
    request = Request(API_URL + path, data=body, headers=headers or {}, method=method)
    try:
        with urlopen(request, timeout=10) as response:
            return response.status, json.loads(response.read())
    except HTTPError as error:
        return error.code, json.loads(error.read())


def upload(filename: str, content: bytes) -> tuple[int, dict[str, object], float]:
    boundary = "Day1" + uuid.uuid4().hex
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
        "Content-Type: text/plain\r\n\r\n"
    ).encode() + content + f"\r\n--{boundary}--\r\n".encode()
    started = time.monotonic()
    status, response = request_json(
        "/documents",
        method="POST",
        body=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    assert isinstance(response, dict)
    return status, response, time.monotonic() - started


def wait_ready(document_id: int) -> dict[str, object]:
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        status, documents = request_json("/documents")
        assert status == 200
        assert isinstance(documents, list)
        document = next((item for item in documents if item["id"] == document_id), None)
        if document is not None and document["status"] in {"ready", "failed"}:
            assert document["status"] == "ready", document
            return document
        time.sleep(0.5)
    pytest.fail("worker did not make the uploaded document ready within 30 seconds")


def test_refactor_regression():
    status, health = request_json("/healthz")
    assert status == 200
    assert health["status"] == "ok"
    status, documents = request_json("/documents")
    assert status == 200
    assert isinstance(documents, list)


def test_empty_input():
    status, response, _ = upload("empty.txt", b"")
    assert status == 422
    assert response["code"] == "invalid_document"


def test_duplicate_or_invalid():
    status, response, _ = upload("invalid.exe", b"not allowed")
    assert status == 400
    assert "Chỉ chấp nhận" in response["detail"]


def test_async_upload():
    status, document, elapsed = upload(f"async-{uuid.uuid4().hex}.txt", b"async contract")
    assert status == 202
    assert elapsed < 1
    assert document["status"] == "pending"
    assert document["chunk_count"] == 0


def test_worker_ingests():
    status, document, _ = upload(
        f"worker-{uuid.uuid4().hex}.txt", b"worker ingests this document"
    )
    assert status == 202
    ready = wait_ready(document["id"])
    assert ready["chunk_count"] > 0
    assert ready["error_code"] is None


def test_retry_idempotent():
    content = b"the same document is safe to process twice"
    status, document, _ = upload(f"retry-{uuid.uuid4().hex}.txt", content)
    assert status == 202
    ready = wait_ready(document["id"])
    command = [
        "docker",
        "compose",
        "-f",
        str(REPO_ROOT / "docker-compose.yml"),
        "exec",
        "-T",
        "ingestion-worker",
        "python",
        "-c",
        (
            "from app.services.ingestion import process_document; "
            f"assert process_document({document['id']}, {document['filename']!r}, {content!r}) == {ready['chunk_count']}"
        ),
    ]
    completed = subprocess.run(command, check=False, capture_output=True, text=True)
    assert completed.returncode == 0, completed.stderr
    repeated = wait_ready(document["id"])
    assert repeated["chunk_count"] == ready["chunk_count"]
