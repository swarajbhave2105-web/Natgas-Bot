"""Run both source-grounded Bull and Bear research agents."""

from __future__ import annotations

from dataclasses import dataclass

from backend.ai.llm_research import LLMResearchResult, run_research_agent
from backend.ai.model_router import ModelRoute, get_active_route, get_routes
from backend.ai.quota_guard import AIQuotaGuard
from backend.ai.research_context import ResearchContext


@dataclass(frozen=True)
class BullBearResearch:
    bull: LLMResearchResult
    bear: LLMResearchResult


async def run_bull_bear_research(
    context: ResearchContext,
    route: ModelRoute | None = None,
    quota_guard: AIQuotaGuard | None = None,
) -> BullBearResearch:
    active_route = route or get_active_route()
    bull = await run_research_agent("bull", context, active_route, quota_guard=quota_guard)
    bear = await run_research_agent("bear", context, active_route, quota_guard=quota_guard)
    return BullBearResearch(bull=bull, bear=bear)

