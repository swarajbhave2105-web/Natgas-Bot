import pandas as pd

from backend.natgas.quant_ensemble import build_technical_evidence


def test_quant_ensemble_produces_technical_evidence():
    rows = []
    for i in range(80):
        base = 300 + i * 0.4
        rows.append(
            {
                "open": base,
                "high": base + 2,
                "low": base - 1,
                "close": base + 1,
            }
        )

    result = build_technical_evidence(pd.DataFrame(rows))

    assert result.role == "technical"
    assert result.direction in {"BULLISH", "BEARISH", "NEUTRAL"}
    assert 0.0 <= result.confidence <= 0.95
    assert result.observations
