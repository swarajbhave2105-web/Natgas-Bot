"""NIFTY analyst pipeline orchestration."""

from dataclasses import dataclass
from typing import Iterable

from backend.nifty.analysts import AnalystEvidence
from backend.nifty.debate import DebateResult, run_debate
from backend.nifty.decision_service import DecisionServiceResult, build_research_decision


@dataclass(frozen=True)
class PipelineResult:
    evidence: tuple[AnalystEvidence, ...]
    debate: DebateResult
    decision: DecisionServiceResult


def run_pipeline(evidence: Iterable[AnalystEvidence]) -> PipelineResult:
    items = tuple(evidence)
    return PipelineResult(
        evidence=items,
        debate=run_debate(items),
        decision=build_research_decision(list(items)),
    )
