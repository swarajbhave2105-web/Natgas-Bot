import pandas as pd

from backend.data.continuous import build_continuous_contract


def test_back_adjustment_removes_roll_gap():
    frame = pd.DataFrame(
        [
            {"timestamp": "2026-01-01", "expiry": "2026-01-25", "open": 100, "high": 101, "low": 99, "close": 100},
            {"timestamp": "2026-01-02", "expiry": "2026-01-25", "open": 101, "high": 102, "low": 100, "close": 101},
            {"timestamp": "2026-01-03", "expiry": "2026-02-25", "open": 111, "high": 112, "low": 110, "close": 111},
            {"timestamp": "2026-01-04", "expiry": "2026-02-25", "open": 112, "high": 113, "low": 111, "close": 112},
        ]
    )

    result = build_continuous_contract(frame, roll_days_before_expiry=0, back_adjust=True)

    # New contract is 10 points above the old one. Earlier history is shifted
    # upward by 10 so the roll itself does not create an artificial return.
    assert result.loc[1, "continuous_close"] == 111
    assert result.loc[2, "continuous_close"] == 111
