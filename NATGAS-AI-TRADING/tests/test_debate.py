from backend.natgas.analysts import AnalystEvidence
from backend.natgas.debate import run_debate


def ev(role, direction, confidence=0.8):
    return AnalystEvidence(role, direction, confidence, [f"{role} observation"], [], [])


def test_debate_keeps_bull_and_bear_cases_separate():
    result = run_debate([
        ev("technical", "BULLISH"),
        ev("weather", "BEARISH"),
        ev("macro", "NEUTRAL"),
    ])
    assert result.bull_score > 0
    assert result.bear_score > 0
    assert result.bull_case
    assert result.bear_case
    assert result.unresolved


def test_debate_does_not_force_balanced_market():
    result = run_debate([
        ev("technical", "BULLISH", 0.5),
        ev("weather", "BEARISH", 0.5),
    ])
    assert result.conclusion.startswith("NO_TRADE")
