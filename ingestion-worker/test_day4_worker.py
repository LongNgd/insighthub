"""Backlog fixture delay serializes jobs while preserving worker execution."""

import asyncio
import os
import threading
import time
import unittest
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

os.environ.update(
    RAG_MODE="fixture", LLM_PROVIDER="fixture", EMBEDDING_PROVIDER="fixture",
    LLM_MODEL="", EMBEDDING_MODEL="", EMBEDDING_DIM="1024",
)

import worker
from app.services.day4_fault import Day4Fault


class BacklogFaultTests(unittest.IsolatedAsyncioTestCase):
    async def test_only_one_fixture_job_processes_at_a_time(self):
        active = 0
        highest = 0
        guard = threading.Lock()

        def process(*_args, **_kwargs):
            nonlocal active, highest
            with guard:
                active += 1
                highest = max(highest, active)
            time.sleep(0.02)
            with guard:
                active -= 1
            return 1

        fault = Day4Fault("backlog", 1.0, datetime.now(UTC) + timedelta(minutes=5))
        with (
            patch.object(worker, "active_fault", return_value=fault),
            patch.object(worker, "process_document", side_effect=process),
            patch.object(worker.asyncio, "sleep", new_callable=AsyncMock) as delay,
        ):
            counts = await asyncio.gather(*(
                worker.process_document_job({"job_try": 1}, number, "fixture.txt", b"fixture")
                for number in range(3)
            ))
        self.assertEqual(counts, [1, 1, 1])
        self.assertEqual(highest, 1)
        self.assertEqual(delay.await_count, 3)

    async def test_off_path_has_no_injected_delay(self):
        with (
            patch.object(worker, "active_fault", return_value=None),
            patch.object(worker, "process_document", return_value=1),
            patch.object(worker.asyncio, "sleep", new_callable=AsyncMock) as delay,
        ):
            count = await worker.process_document_job({"job_try": 1}, 4, "fixture.txt", b"fixture")
        self.assertEqual(count, 1)
        delay.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
