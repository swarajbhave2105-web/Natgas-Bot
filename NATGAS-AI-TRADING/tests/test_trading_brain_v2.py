"""Phase 1 contract tests for the isolated framework-backed NATGAS Brain V2."""
from __future__ import annotations

import pandas as pd
import pytest
from investing_algorithm_framework import SignalSide

from backend.natgas.trading_brain_v2 import BrainV2Config, NatgasTradingBrainV2


def _ohlcv(direction: str = "up", count: int = 50) -> pd.DataFrame:
    """Deterministic synthetic bars; no network data or broker dependency."""
    rows = []
    for i in range(count - 1):
        drift = 0.004 if direction == "up" else -0.004
        oscillation = 0.012 if i % 3 == 0 else (-0.006 if i % 3 == 1 else 0.0)
        close = 100.0 + (i * drift) + oscillation
        open_ = close - 0.003 if i % 2 == 0 else close + 0.002
        high = max(open_, close) + 0.008
        low = min(open_, close) - 0.008
        rows.append((open_, high, low, close, 100 + i))

    # Put the final completed candle beyond the previous 20-bar extreme.
    prior = pd.DataFrame(rows, columns=["open", "high", "low", "close", "volume"])
    if direction == "up":
        close = float(prior["high"].tail(20).max()) + 0.006
        open_ = close - 0.003
    else:
        close = float(prior["low"].tail(20).min()) - 0.006
        open_ = close + 0.003
    rows.append((open_, max(open_, close) + 0.008, min(open_, close) - 0.008, close, 100 + count))
    return pd.DataFrame(rows, columns=["open", "high", "low", "close", "volume"])


def test_requires_minimum_completed_bars() -> None:
    brain = NatgasTradingBrainV2()
    result = brain.evaluate_frame(_ohlcv().head(20))
    assert result["status"] == "NO_TRADE"
    assert result["blockers"] == ["INSUFFICIENT_DATA"]
    assert result["framework_signal"] is None


def test_invalid_price_data_fails_closed() -> None:
    frame = _ohlcv()
    frame.loc[frame.index[-1], "close"] = float("nan")
    result = NatgasTradingBrainV2().evaluate_frame(frame)
    assert result["status"] == "NO_TRADE"
    assert result["blockers"] == ["INVALID_DATA"]


def test_long_breakout_uses_framework_signal_and_trace() -> None:
    result = NatgasTradingBrainV2().evaluate_frame(_ohlcv("up"))
    assert result["direction"] == "LONG"
    assert result["setup_type"] in {"BREAKOUT_CONTINUATION", "BULLISH_REVERSAL", "BULLISH_PULLBACK"}
    assert result["status"] == "ACTIONABLE"
    assert result["risk_reward"] >= 1.8
    signal = result["framework_signal"]
    assert signal is not None
    assert signal["side"] == SignalSide.OPEN_LONG.value
    assert signal["metadata"]["execution_mode"] == "decision_support_only"
    assert result["decision_trace"]["summary"]


def test_short_breakdown_uses_framework_signal_and_trace() -> None:
    result = NatgasTradingBrainV2().evaluate_frame(_ohlcv("down"))
    assert result["direction"] == "SHORT"
    assert result["setup_type"] in {"BREAKDOWN_CONTINUATION", "BEARISH_REVERSAL", "BEARISH_PULLBACK"}
    assert result["status"] == "ACTIONABLE"
    assert result["risk_reward"] >= 1.8
    assert result["framework_signal"]["side"] == SignalSide.OPEN_SHORT.value


def test_generate_signals_returns_intents_only() -> None:
    brain = NatgasTradingBrainV2()
    signals = brain.generate_signals(context=None, data={"NATGAS": _ohlcv("up")})
    assert signals
    assert signals[0].side is SignalSide.OPEN_LONG
    assert signals[0].metadata["execution_mode"] == "decision_support_only"
    assert "decision_trace" in signals[0].metadata


def test_risk_configuration_is_validated() -> None:
    with pytest.raises(ValueError, match="minimum_rr"):
        BrainV2Config(minimum_rr=0.9)
