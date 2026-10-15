"""OpenAI-compatible LLM runner for source-grounded NATGAS research.

Supports OpenAI-compatible endpoints such as OpenRouter and Ollama. Credentials
are read from environment variables and the runner returns text only; it never
places orders or converts model output directly into a trade.
"""

from __future__ import annotations

from dataclasses import dataclass
import os

from backend.ai.agent_prompts import bear_prompt, bull_prompt
from backend.ai.model_router import ModelRoute
from backend.ai.quota_guard import AIQuotaGuard, global_quota_guard
from backend.ai.research_context import ResearchContext


@dataclass(frozen=True)
class LLMResearchResult:
    side: str
    model: str
    text: str
    source_count: int


async def run_research_agent(
    side: str,
    context: ResearchContext,
    route: ModelRoute,
    quota_guard: AIQuotaGuard | None = None,
) -> LLMResearchResult:
    if side not in {"bull", "bear"}:
        raise ValueError("side must be bull or bear")

    guard = quota_guard or global_quota_guard
    prompt = bull_prompt(context) if side == "bull" else bear_prompt(context)
    sources_digest = "".join(f"{s.url}|{s.title};" for s in context.sources)
    cache_key = guard.compute_cache_key(side, route.model, prompt, sources_digest)

    guard.metrics.total_requests += 1

    # Check cache for duplicate calls
    cached = guard.get_cached(cache_key)
    if cached is not None:
        guard.metrics.cache_hits += 1
        return cached

    guard.metrics.cache_misses += 1

    # Check quota availability & circuit breaker
    allowed, quota_reason = guard.check_quota_available()
    if not allowed:
        return LLMResearchResult(
            side=side,
            model=route.model,
            text="",
            source_count=0,
        )

    api_key = _api_key_for(route.provider)
    if not api_key:
        raise RuntimeError(f"Missing API key for provider: {route.provider}")

    try:
        from openai import AsyncOpenAI
    except ImportError as exc:
        raise RuntimeError("openai package is required for LLM research.") from exc

    client = AsyncOpenAI(
        api_key=api_key,
        base_url=route.base_url,
    )

    try:
        response = await client.chat.completions.create(
            model=route.model,
            messages=[
                {"role": "system", "content": "Return research analysis only."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.1,
        )
        text = response.choices[0].message.content or ""
        guard.record_call()
        result = LLMResearchResult(
            side=side,
            model=route.model,
            text=text,
            source_count=len(context.sources),
        )
        guard.set_cached(cache_key, result)
        return result
    except Exception as exc:
        err_msg = str(exc).lower()
        if "429" in err_msg or "rate limit" in err_msg or "quota" in err_msg:
            guard.metrics.rate_limits_encountered += 1
            guard.trip_circuit_breaker()
            return LLMResearchResult(
                side=side,
                model=route.model,
                text="",
                source_count=0,
            )
        raise


def _api_key_for(provider: str) -> str | None:
    normalized = provider.lower()
    if normalized in {"omniroute", "omni"}:
        return (
            os.getenv("OMNIROUTE_API_KEY")
            or os.getenv("NATGAS_OMNIROUTE_API_KEY")
            or os.getenv("OPENROUTER_API_KEY")
            or os.getenv("OPENAI_API_KEY")
            or "omniroute-local"
        )
    if normalized == "openrouter":
        return os.getenv("OPENROUTER_API_KEY")
    if normalized == "ollama":
        return os.getenv("OLLAMA_API_KEY", "ollama")
    return os.getenv("OPENAI_API_KEY")

