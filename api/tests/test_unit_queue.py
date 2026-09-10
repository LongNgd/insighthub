import unittest
from unittest.mock import AsyncMock, patch

from support import configured
from app.core import queue
from app.core.errors import QueueUnavailable


class QueueTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.config = configured()
        self.config.__enter__()
        self.addCleanup(self.config.__exit__, None, None, None)
        queue._redis = None

    async def asyncTearDown(self):
        queue._redis = None

    async def test_enqueue_uses_stable_job_identity(self):
        redis = AsyncMock()
        redis.enqueue_job.return_value = object()
        with patch("app.core.queue.initialize_queue", new=AsyncMock()):
            queue._redis = redis
            await queue.enqueue_ingestion(42, "safe.txt", b"private")
        redis.enqueue_job.assert_awaited_once_with(
            "ingest_document",
            42,
            "safe.txt",
            b"private",
            _job_id="ingestion:42",
        )

    async def test_duplicate_or_failed_enqueue_is_public_safe_error(self):
        redis = AsyncMock()
        redis.enqueue_job.return_value = None
        with patch("app.core.queue.initialize_queue", new=AsyncMock()):
            queue._redis = redis
            with self.assertRaises(QueueUnavailable) as raised:
                await queue.enqueue_ingestion(7, "safe.txt", b"private")
        self.assertEqual(raised.exception.code, "queue_unavailable")
        self.assertNotIn("private", str(raised.exception))
