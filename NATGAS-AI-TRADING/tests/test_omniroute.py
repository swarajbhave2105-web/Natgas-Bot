"""Unit tests for OmniRoute model routing and active selection."""

import os
from unittest.mock import patch

from backend.ai.bull_bear_runner import BullBearResearch, run_bull_bear_research
from backend.ai.model_router import (
    ModelRoute,
    get_active_route,
    get_active_route_name,
    get_routes,
    set_active_route_name,
)
from backend.ai.research_context import ResearchContext, ResearchSource
from backend.ai.llm_research import LLMResearchResult


def test_omniroute_is_default_active_route():
    set_active_route_name(None)
    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("NATGAS_ACTIVE_AI_ROUTE", None)
        assert get_active_route_name() == "omniroute"
        active = get_active_route()
        assert active.provider == "omniroute"
        assert active.base_url == "http://localhost:20128/v1"
        assert active.model == "auto"


def test_omniroute_custom_environment_configuration():
    set_active_route_name(None)
    with patch.dict(
        os.environ,
        {
            "NATGAS_OMNIROUTE_PROVIDER": "omniroute",
            "OMNIROUTE_MODEL": "qwen-2.5-72b",
            "OMNIROUTE_BASE_URL": "http://omniroute.internal:20128/v1",
        },
    ):
        routes = get_routes()
        omni = routes["omniroute"]
        assert omni.provider == "omniroute"
        assert omni.model == "qwen-2.5-72b"
        assert omni.base_url == "http://omniroute.internal:20128/v1"


def test_active_route_fallback_and_selection():
    set_active_route_name(None)
    with patch.dict(os.environ, {"NATGAS_ACTIVE_AI_ROUTE": "llama"}):
        assert get_active_route_name() == "llama"
        active = get_active_route()
        assert active.provider == "openrouter"
        assert "llama" in active.model

    # Unknown route falls back gracefully to omniroute
    with patch.dict(os.environ, {"NATGAS_ACTIVE_AI_ROUTE": "unknown_provider"}):
        active = get_active_route()
        assert active.provider == "omniroute"


async def test_bull_bear_runner_selects_omniroute_by_default():
    set_active_route_name(None)
    captured_routes = []

    async def mock_run_agent(side, context, route, quota_guard=None):
        captured_routes.append(route)
        return LLMResearchResult(
            side=side,
            model=route.model,
            text=f"{side} mock analysis",
            source_count=len(context.sources),
        )

    from backend.ai.research_context import build_research_context

    context = build_research_context(
        query="NATGAS inventory storage",
        sources=(
            ResearchSource(
                title="EIA Weekly Gas Report",
                url="https://eia.gov/dnav/ng/report",
                published_at="2026-10-01",
                source_type="storage",
                relevance=1.0,
            ),
        ),
        evidence=("Storage surplus of 5 Bcf",),
    )

    with patch("backend.ai.bull_bear_runner.run_research_agent", side_effect=mock_run_agent):
        result = await run_bull_bear_research(context)
        assert len(captured_routes) == 2
        # Both bull and bear agents should have used the active omniroute!
        assert captured_routes[0].provider == "omniroute"
        assert captured_routes[1].provider == "omniroute"
        assert result.bull.side == "bull"
        assert result.bear.side == "bear"


async def test_omniroute_openai_request_compatibility():
    """Verify request format, /v1 base_url, model, headers, and parsing."""
    import sys, types
    from unittest.mock import AsyncMock, MagicMock

    if "openai" not in sys.modules:
        openai_mod = types.ModuleType("openai")
        openai_mod.AsyncOpenAI = MagicMock
        sys.modules["openai"] = openai_mod

    from backend.ai.llm_research import run_research_agent
    from backend.ai.quota_guard import AIQuotaGuard
    from backend.ai.research_context import build_research_context


    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_choice = MagicMock()
    mock_choice.message.content = "Bullish gas demand in winter."
    mock_response.choices = [mock_choice]
    mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

    captured_init_kwargs = {}

    def mock_async_openai(**kwargs):
        captured_init_kwargs.update(kwargs)
        return mock_client

    route = ModelRoute(
        provider="omniroute",
        model="omni-test-model",
        base_url="http://localhost:20128/v1",
    )

    context = build_research_context(
        query="NATGAS winter demand",
        sources=(
            ResearchSource(
                title="EIA Outlook",
                url="https://eia.gov/outlook",
                published_at="2026-10-01",
                source_type="report",
                relevance=1.0,
            ),
        ),
        evidence=("Storage withdrawal expected",),
    )

    guard = AIQuotaGuard()

    with patch.dict(os.environ, {"OMNIROUTE_API_KEY": "omni-secret-key"}):
        with patch("backend.ai.llm_research._api_key_for", return_value="omni-secret-key"):
            with patch("openai.AsyncOpenAI", side_effect=mock_async_openai):
                result = await run_research_agent("bull", context, route, quota_guard=guard)

                # 1. Base URL verification - contains exactly one /v1, no double /v1/v1
                assert captured_init_kwargs["base_url"] == "http://localhost:20128/v1"
                assert "/v1/v1" not in captured_init_kwargs["base_url"]

                # 2. Authentication header - uses configured API key
                assert captured_init_kwargs["api_key"] == "omni-secret-key"

                # 3. Call arguments verification
                call_kwargs = mock_client.chat.completions.create.call_args.kwargs
                assert call_kwargs["model"] == "omni-test-model"
                assert call_kwargs["temperature"] == 0.1
                assert len(call_kwargs["messages"]) == 2
                assert call_kwargs["messages"][0]["role"] == "system"
                assert call_kwargs["messages"][1]["role"] == "user"
                assert "NATGAS" in call_kwargs["messages"][1]["content"]

                # 4. Response parsing verification
                assert result.side == "bull"
                assert result.model == "omni-test-model"
                assert result.text == "Bullish gas demand in winter."
                assert result.source_count == 1


async def test_omniroute_429_rate_limit_trips_circuit_breaker():
    """Verify HTTP 429 / rate limit triggers circuit breaker fail-closed safety."""
    import sys, types
    from unittest.mock import AsyncMock, MagicMock

    if "openai" not in sys.modules:
        openai_mod = types.ModuleType("openai")
        openai_mod.AsyncOpenAI = MagicMock
        sys.modules["openai"] = openai_mod

    from backend.ai.llm_research import run_research_agent
    from backend.ai.quota_guard import AIQuotaGuard
    from backend.ai.research_context import build_research_context


    mock_client = MagicMock()
    mock_client.chat.completions.create = AsyncMock(
        side_effect=Exception("Error 429: Rate limit exceeded / quota reached")
    )

    route = ModelRoute(
        provider="omniroute",
        model="auto",
        base_url="http://localhost:20128/v1",
    )

    context = build_research_context(
        query="NATGAS price action",
        sources=(),
        evidence=(),
    )

    guard = AIQuotaGuard(circuit_cooldown_seconds=60.0)
    assert guard.is_circuit_open() is False

    with patch("openai.AsyncOpenAI", return_value=mock_client):
        result = await run_research_agent("bear", context, route, quota_guard=guard)

        # 429 response handled gracefully: returns empty text gap, does NOT crash
        assert result.text == ""
        assert result.source_count == 0
        # Circuit breaker is tripped
        assert guard.is_circuit_open() is True
        assert guard.metrics.rate_limits_encountered == 1

