"""Exercise the ARQ metrics endpoint without starting a database or queue."""

import asyncio
import socket
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from urllib.request import urlopen

import worker


class WorkerMetricsTests(unittest.TestCase):
    def test_metrics_server_reports_worker_readiness(self) -> None:
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            port = listener.getsockname()[1]

        ctx = {}
        settings = SimpleNamespace(worker_metrics_port=port)
        with (
            patch.object(worker, "initialize_database"),
            patch.object(worker, "close_pool"),
            patch.object(worker, "get_settings", return_value=settings),
        ):
            asyncio.run(worker.startup(ctx))
            try:
                with urlopen(f"http://127.0.0.1:{port}/metrics", timeout=2) as response:
                    metrics = response.read().decode("utf-8")
                self.assertIn("insighthub_worker_ready 1.0", metrics)
                self.assertIn('insighthub_worker_jobs_total{outcome="ready"} 0.0', metrics)
            finally:
                asyncio.run(worker.shutdown(ctx))

        self.assertNotIn("metrics_server", ctx)


if __name__ == "__main__":
    unittest.main()
