"""Verify RED timing and token/cost provenance without a database."""

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient
from prometheus_client import generate_latest

from app import main
from app.routers import chat


class DashboardMetricTests(unittest.TestCase):
    def test_http_duration_uses_bounded_route_label(self) -> None:
        with patch.object(main, "initialize_database"), patch.object(main, "close_pool"):
            with TestClient(main.app) as client:
                self.assertEqual(client.get("/").status_code, 200)
        metrics = generate_latest().decode()
        self.assertIn(
            'insighthub_http_request_duration_seconds_count{endpoint="/",method="GET",status="200"}',
            metrics,
        )

    def test_fixture_usage_is_estimated_and_cost_is_zero(self) -> None:
        result = {
            "answer": "fixture answer",
            "sources": ["test.txt"],
            "mode": "fixture",
            "provider": "fixture",
            "model": "extractive-fixture-v1",
            "usage": {"input_tokens": None, "output_tokens": None, "source": "unavailable"},
        }
        with (
            patch.object(chat, "retrieve", return_value=[{"chunk_text": "real test context", "source": "test.txt"}]),
            patch.object(chat, "generate", return_value=result),
        ):
            response = chat.chat(chat.ChatRequest(question="test question"))
        self.assertEqual(response.usage.source, "unavailable")
        metrics = generate_latest().decode()
        self.assertIn(
            'insighthub_llm_estimated_tokens_total{direction="input",provider="fixture"}',
            metrics,
        )
        self.assertIn(
            'insighthub_llm_estimated_cost_usd_total{provider="fixture",usage_source="no_provider_charge"} 0.0',
            metrics,
        )

    def test_provider_usage_cost_uses_configured_rates(self) -> None:
        result = {
            "answer": "provider answer",
            "sources": ["test.txt"],
            "mode": "real",
            "provider": "openai",
            "model": "example-model",
            "usage": {"input_tokens": 100, "output_tokens": 50, "source": "provider"},
        }
        settings = SimpleNamespace(
            llm_input_usd_per_million_tokens=1.0,
            llm_output_usd_per_million_tokens=2.0,
        )
        with (
            patch.object(chat, "retrieve", return_value=[{"chunk_text": "context", "source": "test.txt"}]),
            patch.object(chat, "generate", return_value=result),
            patch.object(chat, "get_settings", return_value=settings),
        ):
            chat.chat(chat.ChatRequest(question="test question"))
        metrics = generate_latest().decode()
        self.assertIn(
            'insighthub_llm_estimated_cost_usd_total{provider="openai",usage_source="provider"} 0.0002',
            metrics,
        )


if __name__ == "__main__":
    unittest.main()
