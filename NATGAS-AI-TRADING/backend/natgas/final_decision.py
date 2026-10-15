"""Final deterministic NATGAS Trader + Risk decision engine.

This layer converts validated analyst/debate evidence plus a supplied live price
and ATR into a structured research decision. It never places an order.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from backend.natgas.analysts import AnalystEvidence
from backend.natgas.debate import DebateResult
from backend.natgas.risk import assess
from backend.natgas.signal import NatgasDecision


@dataclass(frozen=True)
class FinalDecisionInput:
    current_price: float
    atr: float | None
    regime: str
    evidence: tuple[AnalystEvidence, ...]
    debate: DebateResult
    catalysts: tuple[str, ...] = ()
    risks: tuple[str, ...] = ()


def build_final_decision(data: FinalDecisionInput) -> NatgasDecision:
    """Return a research-only final decision with explicit risk geometry.

    Hard gates:
    - invalid/non-positive price or ATR => NO_TRADE
    - unresolved analyst data gaps => NO_TRADE
    - balanced/conflicting bull-vs-bear evidence => NO_TRADE
    - risk geometry must pass before LONG/SHORT can be emitted
    """
    if data.current_price <= 0:
        return _no_trade("Current price is missing or invalid.")

    if data.atr is None or data.atr <= 0:
        return _no_trade("ATR is missing or invalid; risk geometry cannot be established.")

    gaps = [f"{item.role}: {gap}" for item in data.evidence for gap in item.data_gaps]
    if gaps:
        return _no_trade("Required evidence has unresolved data gaps.", gaps)

    if data.debate.conclusion.startswith("NO_TRADE"):
        return _no_trade(data.debate.conclusion, list(data.debate.unresolved))

    if data.debate.bull_score == data.debate.bear_score:
        return _no_trade("Bull and bear evidence are balanced.")

    confidence = _bounded_confidence(data.debate)
    if confidence < 0.60:
        return _no_trade("Final evidence confidence is below the research threshold.")

    direction = "LONG" if data.debate.bull_score > data.debate.bear_score else "SHORT"
    entry = data.current_price
    atr = data.atr

    if direction == "LONG":
        invalidation = entry - 1.0 * atr
        target1 = entry + 1.5 * atr
        target2 = entry + 2.5 * atr
    else:
        invalidation = entry + 1.0 * atr
        target1 = entry - 1.5 * atr
        target2 = entry - 2.5 * atr

    risk = assess(
        direction=direction,
        entry=entry,
        invalidation=invalidation,
        target=target1,
    )
    if not risk.approved_for_research:
        return _no_trade("Risk geometry failed validation.", risk.reasons)

    rr = 1.5
    regime_text = data.regime or "UNKNOWN"
    rationale = [
        f"Market regime: {regime_text}.",
        data.debate.conclusion,
        f"Research risk geometry uses 1.0 ATR invalidation and {rr:.1f}R first target.",
    ]

    return NatgasDecision(
        instrument="MCX_NATGAS",
        direction=direction,
        confidence=confidence,
        entry_zone=_zone(entry, atr),
        invalidation=f"{invalidation:.2f}",
        targets=[f"{target1:.2f}", f"{target2:.2f}"],
        rationale=rationale,
        catalysts=list(data.catalysts)[:5],
        risks=list(data.risks)[:5] + list(data.debate.unresolved)[:3],
    )


def _bounded_confidence(debate: DebateResult) -> float:
    total = debate.bull_score + debate.bear_score
    if total <= 0:
        return 0.0
    dominance = abs(debate.bull_score - debate.bear_score) / total
    return round(min(0.95, 0.60 + 0.35 * dominance), 4)


def _zone(price: float, atr: float) -> str:
    half_width = 0.20 * atr
    return f"{price - half_width:.2f}-{price + half_width:.2f}"


def _no_trade(reason: str, risks: Iterable[str] = ()) -> NatgasDecision:
    return NatgasDecision(
        direction="NO_TRADE",
        confidence=0.0,
        rationale=[reason],
        risks=list(risks)[:5],
    )
