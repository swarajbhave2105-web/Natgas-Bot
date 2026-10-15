"""Deterministic NATGAS decision service boundary.

AI agents provide evidence; this service decides whether that evidence is
complete enough to produce a research decision. It never places orders.
"""

from dataclasses import dataclass

from backend.natgas.analysts import AnalystEvidence
from backend.natgas.decision import build_decision


@dataclass(frozen=True)
class DecisionServiceResult:
    decision: object
    evidence_count: int


REQUIRED_ROLES = {"technical", "fundamental", "weather", "macro", "news", "risk"}


def build_research_decision(evidence: list[AnalystEvidence]) -> DecisionServiceResult:
    roles = {str(item.role) for item in evidence}
    missing = REQUIRED_ROLES - roles
    if missing:
        return DecisionServiceResult(
            decision=build_decision(
                bullish_evidence=[], bearish_evidence=[], confidence=0.0,
            ),
            evidence_count=len(evidence),
        )

    bullish = [obs for item in evidence if item.direction == "BULLISH" for obs in item.observations]
    bearish = [obs for item in evidence if item.direction == "BEARISH" for obs in item.observations]
    confidences = [max(0.0, min(1.0, item.confidence)) for item in evidence]

    return DecisionServiceResult(
        decision=build_decision(
            bullish_evidence=bullish,
            bearish_evidence=bearish,
            confidence=min(confidences) if confidences else 0.0,
        ),
        evidence_count=len(evidence),
    )
