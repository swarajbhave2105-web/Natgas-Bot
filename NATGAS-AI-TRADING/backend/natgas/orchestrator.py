"""Deterministic orchestration skeleton for future AI analysts."""

from backend.natgas.analysts import AnalystEvidence
from backend.natgas.decision import build_decision
from backend.natgas.signal import NatgasDecision


def aggregate_evidence(evidence: list[AnalystEvidence]) -> NatgasDecision:
    bullish: list[str] = []
    bearish: list[str] = []
    confidences: list[float] = []

    for item in evidence:
        confidences.append(item.confidence)
        if item.direction == "BULLISH":
            bullish.extend(item.observations)
        elif item.direction == "BEARISH":
            bearish.extend(item.observations)

    confidence = min(confidences) if confidences else 0.0
    return build_decision(
        bullish_evidence=bullish,
        bearish_evidence=bearish,
        confidence=confidence,
    )
