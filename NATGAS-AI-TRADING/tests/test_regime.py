from backend.natgas.regime import classify_regime


def test_bullish_regime():
    result = classify_regime(5.0, 4.8, 4.5)
    assert result.regime == "BULLISH_TREND"


def test_bearish_regime():
    result = classify_regime(4.0, 4.2, 4.5)
    assert result.regime == "BEARISH_TREND"


def test_mixed_regime():
    result = classify_regime(4.5, 4.8, 4.2)
    assert result.regime == "MIXED"


def test_insufficient_data():
    result = classify_regime(4.5, None, None)
    assert result.regime == "INSUFFICIENT_DATA"
