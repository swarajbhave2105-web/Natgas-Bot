"""Async research-aware NIFTY pipeline entry point."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from backend.ai.bull_bear_runner import BullBearResearch, run_bull_bear_research
from backend.ai.research import ResearchProvider
from backend.ai.runtime_research import build_context
from backend.nifty.analysts import AnalystEvidence
from backend.nifty.debate import DebateResult, run_debate
from backend.nifty.decision_service import DecisionServiceResult, build_research_decision
from backend.nifty.llm_evidence import research_to_evidence


@dataclass(frozen=True)
class ResearchPipelineResult:
    research: BullBearResearch
    evidence: tuple[AnalystEvidence, ...]
    debate: DebateResult
    decision: DecisionServiceResult


async def run_research_pipeline(
    provider: ResearchProvider,
    query: str,
    market_evidence: Iterable[str] = (),
    existing_evidence: Iterable[AnalystEvidence] = (),
    limit: int = 8,
) -> ResearchPipelineResult:
    context = await build_context(provider, query, tuple(market_evidence), limit)
    research = await run_bull_bear_research(context)
    llm_evidence = research_to_evidence(research)
    evidence = tuple(existing_evidence) + tuple(llm_evidence)
    debate = run_debate(evidence)
    decision = build_research_decision(list(evidence))
    return ResearchPipelineResult(
        research=research,
        evidence=evidence,
        debate=debate,
        decision=decision,
    )
