"""RAG executes in FastAPI's threadpool; usage preserves its provenance."""

import time
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from app.core.config import get_settings
from app.core.metrics import (
    llm_call_latency,
    llm_estimated_cost_usd_total,
    llm_estimated_tokens_total,
    llm_tokens_total,
    rag_query_latency,
)
from app.services.llm import generate
from app.services.retrieval import retrieve

router = APIRouter(prefix="/chat", tags=["chat"])


def _estimated_tokens(text: str) -> float:
    """Word-based estimate only; never treat this as provider billing usage."""
    return len(text.split()) / 0.75


class ChatRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    question: str = Field(min_length=1, max_length=2000)
    top_k: int | None = Field(default=None, ge=1, le=20)


class TokenUsage(BaseModel):
    input_tokens: int | None = None
    output_tokens: int | None = None
    source: Literal["provider", "unavailable"]


class ChatResponse(BaseModel):
    answer: str
    sources: list[str]
    contexts: list[dict]
    latency_ms: int
    mode: Literal["fixture", "real"]
    provider: str
    model: str
    usage: TokenUsage


@router.post("", response_model=ChatResponse)
def chat(req: ChatRequest):
    start = time.perf_counter()
    with rag_query_latency.time():
        contexts = retrieve(req.question, top_k=req.top_k)
        if not contexts:
            raise HTTPException(
                404, "Chưa có tài liệu nào sẵn sàng. Hãy upload tài liệu trước."
            )
        with llm_call_latency.time():
            result = generate(req.question, contexts)
    estimated_input = _estimated_tokens(req.question) + sum(
        _estimated_tokens(context["chunk_text"]) for context in contexts
    )
    estimated_output = _estimated_tokens(result["answer"])
    usage_for_cost: dict[str, float] = {}
    for direction, estimate in (("input", estimated_input), ("output", estimated_output)):
        value = result["usage"].get(f"{direction}_tokens")
        if value is not None:
            llm_tokens_total.labels(result["provider"], direction).inc(value)
            usage_for_cost[direction] = value
        else:
            llm_estimated_tokens_total.labels(result["provider"], direction).inc(estimate)
            usage_for_cost[direction] = estimate
    if result["mode"] == "fixture":
        llm_estimated_cost_usd_total.labels("fixture", "no_provider_charge").inc(0)
    else:
        settings = get_settings()
        input_rate = settings.llm_input_usd_per_million_tokens
        output_rate = settings.llm_output_usd_per_million_tokens
        if input_rate > 0 and output_rate > 0:
            usage_source = (
                "provider"
                if all(
                    result["usage"].get(f"{direction}_tokens") is not None
                    for direction in ("input", "output")
                )
                else "estimated"
            )
            cost = (
                usage_for_cost["input"] * input_rate
                + usage_for_cost["output"] * output_rate
            ) / 1_000_000
            llm_estimated_cost_usd_total.labels(result["provider"], usage_source).inc(cost)
    return ChatResponse(
        **result,
        contexts=contexts,
        latency_ms=int((time.perf_counter() - start) * 1000),
    )
