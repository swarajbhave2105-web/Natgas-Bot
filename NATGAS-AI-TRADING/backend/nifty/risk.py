"""NIFTY risk gate.

This module does not size a real order. It checks whether a proposed research
decision has enough information to describe risk before a future backtest.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class RiskAssessment:
    approved_for_research: bool
    reasons: list[str]


def assess(
    *,
    direction: str,
    entry: float | None,
    invalidation: float | None,
    target: float | None,
) -> RiskAssessment:
    reasons: list[str] = []

    if direction not in {"LONG", "SHORT"}:
        return RiskAssessment(True, ["No directional position proposed."])

    if None in {entry, invalidation, target}:
        return RiskAssessment(False, ["Entry, invalidation and target are required."])

    if direction == "LONG" and not (invalidation < entry < target):
        reasons.append("LONG geometry requires invalidation < entry < target.")
    if direction == "SHORT" and not (target < entry < invalidation):
        reasons.append("SHORT geometry requires target < entry < invalidation.")

    return RiskAssessment(not reasons, reasons or ["Risk geometry is internally consistent."])
