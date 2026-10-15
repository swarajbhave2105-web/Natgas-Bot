"""Transparent evidence-to-decision gate for NATGAS."""

from backend.natgas.signal import NatgasDecision


def build_decision(
    *,
    bullish_evidence: list[str],
    bearish_evidence: list[str],
    confidence: float,
) -> NatgasDecision:
    if not bullish_evidence and not bearish_evidence:
        return NatgasDecision(
            direction="NO_TRADE",
            confidence=0,
            rationale=["No validated evidence available."],
        )

    # Do not force a trade when the evidence is materially conflicting.
    if bullish_evidence and bearish_evidence:
        return NatgasDecision(
            direction="NO_TRADE",
            confidence=min(confidence, 0.50),
            rationale=[
                "Bullish and bearish evidence are both present.",
                "Waiting for alignment is required.",
            ],
            catalysts=bullish_evidence[:3],
            risks=bearish_evidence[:3],
        )

    direction = "LONG" if bullish_evidence else "SHORT"
    evidence = bullish_evidence or bearish_evidence
    return NatgasDecision(
        direction=direction,
        confidence=confidence,
        rationale=evidence,
    )
