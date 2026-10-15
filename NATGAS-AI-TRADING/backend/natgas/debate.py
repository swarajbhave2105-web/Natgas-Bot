"""NATGAS bull-vs-bear research debate.

This is a deterministic evidence synthesis layer. LLM research can consume the
structured cases later, but this layer never invents facts or forces a trade.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from backend.natgas.analysts import AnalystEvidence


@dataclass(frozen=True)
class DebateResult:
    bull_case: tuple[str, ...]
    bear_case: tuple[str, ...]
    unresolved: tuple[str, ...]
    bull_score: float
    bear_score: float
    conclusion: str


def run_debate(evidence: Iterable[AnalystEvidence]) -> DebateResult:
    items = tuple(evidence)
    bull_case: list[str] = []
    bear_case: list[str] = []
    unresolved: list[str] = []

    for item in items:
        if item.direction == "BULLISH":
            bull_case.extend(f"{item.role}: {obs}" for obs in item.observations)
        elif item.direction == "BEARISH":
            bear_case.extend(f"{item.role}: {obs}" for obs in item.observations)
        else:
            unresolved.extend(f"{item.role}: {obs}" for obs in item.observations)

        unresolved.extend(f"{item.role} data gap: {gap}" for gap in item.data_gaps)
        unresolved.extend(f"{item.role} risk: {risk}" for risk in item.risks)

    bull_score = sum(
        max(0.0, min(1.0, item.confidence))
        for item in items
        if item.direction == "BULLISH"
    )
    bear_score = sum(
        max(0.0, min(1.0, item.confidence))
        for item in items
        if item.direction == "BEARISH"
    )

    if not items:
        conclusion = "NO_TRADE: no analyst evidence."
    elif bull_score == bear_score:
        conclusion = "NO_TRADE: bull and bear evidence are balanced."
    elif unresolved and abs(bull_score - bear_score) < 0.20:
        conclusion = "NO_TRADE: directional evidence is too close and unresolved risks remain."
    elif bull_score > bear_score:
        conclusion = "BULL_CASE_LEADS: bull evidence currently outweighs bear evidence."
    else:
        conclusion = "BEAR_CASE_LEADS: bear evidence currently outweighs bull evidence."

    return DebateResult(
        bull_case=tuple(bull_case),
        bear_case=tuple(bear_case),
        unresolved=tuple(unresolved),
        bull_score=round(bull_score, 4),
        bear_score=round(bear_score, 4),
        conclusion=conclusion,
    )
