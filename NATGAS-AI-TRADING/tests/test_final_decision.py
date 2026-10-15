"""Tests for the final NATGAS Trader + Risk engine."""

from backend.natgas.analysts import AnalystEvidence
from backend.natgas.debate import run_debate
from backend.natgas.final_decision import FinalDecisionInput, build_final_decision


def ev(role, direction, confidence=0.9):
    return AnalystEvidence(
        role=role,
        direction=direction,
        confidence=confidence,
        observations=[f"{role} observation"],
        data_gaps=[],
        risks=[],
    )


def test_final_engine_emits_structured_long_with_risk_geometry():
    evidence = (
        ev("technical", "BULLISH"),
        ev("fundamental", "BULLISH"),
        ev("weather", "BULLISH"),
    )
    debate = run_debate(evidence)
    decision = build_final_decision(
        FinalDecisionInput(
            current_price=300.0,
            atr=10.0,
            regime="BULLISH_TREND",
            evidence=evidence,
            debate=debate,
            catalysts=("Storage/demand evidence supports the case.",),
        )
    )

    assert decision.direction == "LONG"
    assert decision.entry_zone == "298.00-302.00"
    assert decision.invalidation == "290.00"
    assert decision.targets == ["315.00", "325.00"]
    assert decision.confidence >= 0.60


def test_final_engine_emits_no_trade_for_conflict():
    evidence = (
        ev("technical", "BULLISH"),
        ev("weather", "BEARISH"),
    )
    debate = run_debate(evidence)
    decision = build_final_decision(
        FinalDecisionInput(
            current_price=300.0,
            atr=10.0,
            regime="MIXED",
            evidence=evidence,
            debate=debate,
        )
    )

    assert decision.direction == "NO_TRADE"


def test_final_engine_emits_no_trade_without_atr():
    evidence = (ev("technical", "BULLISH"),)
    debate = run_debate(evidence)
    decision = build_final_decision(
        FinalDecisionInput(
            current_price=300.0,
            atr=None,
            regime="BULLISH_TREND",
            evidence=evidence,
            debate=debate,
        )
    )

    assert decision.direction == "NO_TRADE"
