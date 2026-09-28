"""The Day 4 fault switch must be bounded and inert outside kind fixture mode."""

import json
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from support import configured, real_config
from app.core.errors import ProviderError
from app.main import app
from app.services.day4_fault import active_fault
from app.services.llm import generate


class Day4FaultTests(unittest.TestCase):
    contexts = [{"source": "fixture.txt", "chunk_text": "Fixture content."}]

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "fault.json"

    def write(self, mode: str, delay_seconds: float, expires_at: datetime):
        self.path.write_text(json.dumps({
            "mode": mode,
            "delay_seconds": delay_seconds,
            "expires_at": expires_at.isoformat(),
        }))

    def fault_settings(self):
        return configured(
            environment="day4-kind",
            day4_chaos_enabled=True,
            day4_chaos_control_path=str(self.path),
        )

    def test_default_off_and_real_mode_rejected(self):
        self.write("latency", 3, datetime.now(UTC) + timedelta(minutes=5))
        with configured(environment="day4-kind", day4_chaos_control_path=str(self.path)):
            self.assertIsNone(active_fault())
        with self.assertRaises(ValueError):
            with real_config(
                environment="day4-kind", day4_chaos_enabled=True,
                day4_chaos_control_path=str(self.path),
            ):
                pass

    def test_invalid_or_stale_control_is_off(self):
        now = datetime.now(UTC)
        with self.fault_settings():
            for mode, delay, expiry in (
                ("off", 0, now + timedelta(minutes=5)),
                ("latency", 31, now + timedelta(minutes=5)),
                ("backlog", 0, now + timedelta(minutes=5)),
                ("errors", 1, now + timedelta(minutes=5)),
                ("errors", 0, now - timedelta(seconds=1)),
                ("errors", 0, now + timedelta(minutes=16)),
            ):
                with self.subTest(mode=mode, delay=delay, expiry=expiry):
                    self.write(mode, delay, expiry)
                    self.assertIsNone(active_fault(now))
            self.path.write_text("not-json")
            self.assertIsNone(active_fault(now))
            self.path.write_bytes(b"x" * 1025)
            self.assertIsNone(active_fault(now))
            self.path.unlink()
            self.assertIsNone(active_fault(now))

    def test_latency_only_sleeps_in_fixture(self):
        self.write("latency", 3, datetime.now(UTC) + timedelta(minutes=5))
        with self.fault_settings(), patch("app.services.llm.time.sleep") as sleep:
            result = generate("question", self.contexts)
        sleep.assert_called_once_with(3.0)
        self.assertEqual(result["mode"], "fixture")
        self.assertIn("FIXTURE", result["answer"])

    def test_error_uses_existing_sanitized_provider_contract(self):
        self.write("errors", 0, datetime.now(UTC) + timedelta(minutes=5))
        with self.fault_settings(), self.assertRaises(ProviderError):
            generate("question", self.contexts)

    def test_error_burst_returns_sanitized_http_502(self):
        self.write("errors", 0, datetime.now(UTC) + timedelta(minutes=5))
        with self.fault_settings(), patch("app.routers.chat.retrieve", return_value=self.contexts):
            response = TestClient(app).post("/chat", json={"question": "fixture question"})
        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.json()["code"], "provider_error")
        self.assertNotIn("fault.json", response.text)


if __name__ == "__main__":
    unittest.main()
