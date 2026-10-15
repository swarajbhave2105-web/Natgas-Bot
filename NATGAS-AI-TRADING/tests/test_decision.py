from backend.natgas.decision import build_decision


def test_conflict_means_no_trade():
    result = build_decision(
        bullish_evidence=["Trend is bullish."],
        bearish_evidence=["Weather signal is bearish."],
        confidence=0.8,
    )
    assert result.direction == "NO_TRADE"


def test_single_side_can_produce_direction():
    result = build_decision(
        bullish_evidence=["Momentum is positive."],
        bearish_evidence=[],
        confidence=0.75,
    )
    assert result.direction == "LONG"
