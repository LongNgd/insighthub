"""Exercise the ARQ metrics endpoint without starting a database or queue."""

import asyncio
import socket
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch
from urllib.request import urlopen

import worker


class WorkerMetricsTests(unittest.TestCase):
    def test_metrics_server_reports_worker_readiness(self) -> None:
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            port = listener.getsockname()[1]

        redis = SimpleNamespace(zcard=AsyncMock(return_value=3))
        ctx = {"redis": redis}
        settings = SimpleNamespace(worker_metrics_port=port)
        async def check_metrics() -> None:
            await worker.startup(ctx)
            try:
                await asyncio.sleep(0.01)
                with urlopen(f"http://127.0.0.1:{port}/metrics", timeout=2) as response:
                    metrics = response.read().decode("utf-8")
                self.assertIn("insighthub_worker_ready 1.0", metrics)
                self.assertIn('insighthub_worker_jobs_total{outcome="ready"} 0.0', metrics)
                self.assertIn("insighthub_worker_queue_entries 3.0", metrics)
                self.assertIn("insighthub_worker_queue_probe_success 1.0", metrics)
                redis.zcard.assert_awaited_with(worker.default_queue_name)
            finally:
                await worker.shutdown(ctx)

        with (
            patch.object(worker, "initialize_database"),
            patch.object(worker, "close_pool"),
            patch.object(worker, "get_settings", return_value=settings),
        ):
            asyncio.run(check_metrics())

        self.assertNotIn("metrics_server", ctx)


if __name__ == "__main__":
    unittest.main()
