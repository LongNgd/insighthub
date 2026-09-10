import unittest
from unittest.mock import patch

from arq import Retry

from support import configured
from app.core.errors import InvalidDocument, ProviderError
from app.services.ingestion_worker import ingest_document


class WorkerTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.config = configured()
        self.config.__enter__()
        self.addCleanup(self.config.__exit__, None, None, None)

    async def test_invalid_document_is_not_retried(self):
        with patch(
            "app.services.ingestion_worker.process_document",
            side_effect=InvalidDocument(),
        ) as process:
            with self.assertRaises(InvalidDocument):
                await ingest_document({"job_try": 1}, 1, "bad.txt", b" ")
        process.assert_called_once()

    async def test_transient_failure_retries_with_exponential_backoff(self):
        for attempt, delay in ((1, 1), (2, 2)):
            with patch(
                "app.services.ingestion_worker.process_document",
                side_effect=ProviderError(),
            ):
                with self.assertRaises(Retry) as raised:
                    await ingest_document(
                        {"job_try": attempt}, 1, "test.txt", b"content"
                    )
            self.assertEqual(raised.exception.defer_score, delay * 1000)

    async def test_third_transient_failure_is_final(self):
        with patch(
            "app.services.ingestion_worker.process_document",
            side_effect=ProviderError(),
        ) as process:
            with self.assertRaises(ProviderError):
                await ingest_document({"job_try": 3}, 1, "test.txt", b"content")
        process.assert_called_once()
