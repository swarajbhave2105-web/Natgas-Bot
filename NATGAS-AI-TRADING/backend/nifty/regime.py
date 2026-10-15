"""Market-regime logic kept deterministic and auditable."""

from dataclasses import dataclass


@dataclass(frozen=True)
class RegimeResult:
    regime: str
    rationale: list[str]


def classify_regime(close: float, sma_20: float | None, sma_50: float | None) -> RegimeResult:
    if sma_20 is None or sma_50 is None:
        return RegimeResult("INSUFFICIENT_DATA", ["Not enough moving-average history."])
    if close > sma_20 > sma_50:
        return RegimeResult("BULLISH_TREND", ["Price > SMA20 > SMA50."])
    if close < sma_20 < sma_50:
        return RegimeResult("BEARISH_TREND", ["Price < SMA20 < SMA50."])
    return RegimeResult("MIXED", ["Trend signals are not aligned."])
