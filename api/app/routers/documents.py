"""Asynchronous upload endpoint backed by the durable Redis queue."""

from datetime import datetime, time, timedelta, timezone

from fastapi import APIRouter, HTTPException, UploadFile
from starlette.concurrency import run_in_threadpool

from app.core.config import get_settings
from app.core.db import get_conn
from app.core.errors import InvalidDocument
from app.services.queue import enqueue_document

router = APIRouter(prefix="/documents", tags=["documents"])
ALLOWED_EXT = (".txt", ".md", ".pdf")


def _create_pending_document(filename: str) -> int:
    with get_conn() as conn:
        return conn.execute(
            "INSERT INTO documents (filename, status) VALUES (%s, 'pending') RETURNING id",
            (filename,),
        ).fetchone()[0]


def _delete_pending_document(document_id: int) -> None:
    with get_conn() as conn:
        conn.execute("DELETE FROM documents WHERE id = %s AND status = 'pending'", (document_id,))


def _utc_day_bounds(now: datetime | None = None) -> tuple[datetime, datetime]:
    """Return the half-open UTC interval for ``now`` without local-time ambiguity."""

    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    current_utc = current.astimezone(timezone.utc)
    start = datetime.combine(current_utc.date(), time.min, tzinfo=timezone.utc)
    return start, start + timedelta(days=1)


def _format_utc(value: datetime) -> str:
    """Serialize a UTC timestamp with an explicit Z suffix."""

    return value.isoformat().replace("+00:00", "Z")


@router.post("", status_code=202)
async def upload_document(file: UploadFile):
    try:
        if not file.filename or not file.filename.lower().endswith(ALLOWED_EXT):
            raise HTTPException(400, "Chỉ chấp nhận: .txt, .md, .pdf")
        if len(file.filename) > 255 or "\x00" in file.filename:
            raise HTTPException(422, "Tên file không hợp lệ.")
        content = file.file.read(get_settings().max_upload_bytes + 1)
    finally:
        file.file.close()
    if len(content) > get_settings().max_upload_bytes:
        raise HTTPException(413, "File vượt quá giới hạn upload.")
    if not content:
        raise InvalidDocument()
    document_id = await run_in_threadpool(_create_pending_document, file.filename)
    try:
        await enqueue_document(document_id, file.filename, content)
    except Exception:
        await run_in_threadpool(_delete_pending_document, document_id)
        raise
    settings = get_settings()
    return {
        "id": document_id,
        "filename": file.filename,
        "status": "pending",
        "chunk_count": 0,
        "mode": settings.rag_mode,
        "embedding_identity_id": settings.embedding_identity_id,
    }


@router.get("")
def list_documents():
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT id, filename, status, chunk_count, created_at, "
            "embedding_identity_id, error_code FROM documents ORDER BY created_at DESC"
        ).fetchall()
    return [
        {
            "id": r[0],
            "filename": r[1],
            "status": r[2],
            "chunk_count": r[3],
            "created_at": r[4].isoformat(),
            "embedding_identity_id": r[5],
            "error_code": r[6],
        }
        for r in rows
    ]


@router.get("/ingest-count/today-utc")
def ingest_count_today_utc() -> dict[str, str | int]:
    """Count documents created during the current UTC day without exposing metadata."""

    interval_start, interval_end = _utc_day_bounds()
    with get_conn() as conn:
        count = conn.execute(
            "SELECT count(*) FROM documents "
            "WHERE created_at >= %s AND created_at < %s",
            (interval_start, interval_end),
        ).fetchone()[0]
    return {
        "date_utc": interval_start.date().isoformat(),
        "interval_start_utc": _format_utc(interval_start),
        "interval_end_utc": _format_utc(interval_end),
        "count": count,
    }


@router.delete("/{document_id}", status_code=204)
def delete_document(document_id: int):
    with get_conn() as conn:
        result = conn.execute(
            "DELETE FROM documents WHERE id = %s RETURNING id",
            (document_id,),
        ).fetchone()
    if result is None:
        raise HTTPException(404, "Không tìm thấy tài liệu.")
