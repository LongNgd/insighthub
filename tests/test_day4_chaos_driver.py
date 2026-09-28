"""Guardrails for the local Day 4 incident driver."""

import importlib.util
import unittest
from pathlib import Path
from unittest.mock import patch


PATH = Path(__file__).resolve().parents[1] / "scripts/chaos/run-day4.py"
SPEC = importlib.util.spec_from_file_location("run_day4", PATH)
driver = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(driver)


class ChaosDriverTests(unittest.TestCase):
    def test_only_local_port_forwards_are_accepted(self):
        self.assertEqual(driver.local_url("http://127.0.0.1:19090/"), "http://127.0.0.1:19090")
        for url in ("https://127.0.0.1:19090", "http://example.com", "http://10.0.0.1"):
            with self.subTest(url=url), self.assertRaises(ValueError):
                driver.local_url(url)

    def test_incident_rejects_active_silence(self):
        active = {"status": {"state": "active"}}
        expired = {"status": {"state": "expired"}}
        with patch.object(driver, "json_request", return_value=(200, [expired])):
            driver.ensure_no_active_silences("http://127.0.0.1:19093")
        with patch.object(driver, "json_request", return_value=(200, [active])), self.assertRaises(RuntimeError):
            driver.ensure_no_active_silences("http://127.0.0.1:19093")
        with patch.object(driver, "json_request", return_value=(503, [])), self.assertRaises(RuntimeError):
            driver.ensure_no_active_silences("http://127.0.0.1:19093")

    def test_preflight_rejects_missing_baseline_and_active_alert(self):
        def good_query(_url, expression):
            if expression.startswith("up{"):
                return [{"value": [0, "1"]}] * 5
            return [{"value": [0, "1"]}]
        with patch.object(driver, "prom_query", side_effect=good_query), patch.object(driver, "current_alerts", return_value={}):
            driver.preflight("http://127.0.0.1:19090")
        with patch.object(driver, "prom_query", return_value=[]), self.assertRaises(RuntimeError):
            driver.preflight("http://127.0.0.1:19090")
        with patch.object(driver, "prom_query", side_effect=good_query), patch.object(
            driver, "current_alerts", return_value={driver.ALERTS["errors"]: "firing"}
        ), self.assertRaises(RuntimeError):
            driver.preflight("http://127.0.0.1:19090")

    def test_recovery_requires_normal_value_even_if_band_expands(self):
        def inflated_band(_url, expression):
            return [{"value": [0, "3" if ":current" in expression else "10"]}]
        with (
            patch.object(driver, "prom_query", side_effect=inflated_band),
            patch.object(driver, "current_alerts", return_value={}),
            patch.object(driver.time, "monotonic", side_effect=[0, 0, 901]),
            patch.object(driver.time, "sleep"),
            self.assertRaises(RuntimeError),
        ):
            driver.wait_recovery("http://127.0.0.1:18000", "http://127.0.0.1:19090", "backlog")

    def test_backlog_recovery_requires_document_ready(self):
        ready = [{"id": 9, "status": "ready"}, {"id": 10, "status": "ready"}]
        with patch.object(driver, "json_request", return_value=(200, ready)):
            self.assertTrue(driver.wait_documents_ready("http://127.0.0.1:18000", [9, 10]))
        failed = [{"id": 9, "status": "ready"}, {"id": 10, "status": "failed"}]
        with patch.object(driver, "json_request", return_value=(200, failed)), self.assertRaises(RuntimeError):
            driver.wait_documents_ready("http://127.0.0.1:18000", [9, 10])


if __name__ == "__main__":
    unittest.main()
