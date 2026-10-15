"""NATGAS technical evidence adapter built from deterministic quant features."""

from __future__ import annotations

import pandas as pd

from backend.indicators.technical import add_basic_indicators, add_quant_trading_indicators
from backend.natgas.analysts import AnalystEvidence


def build_technical_evidence(df: pd.DataFrame) -> AnalystEvidence:
    """Convert the latest validated OHLCV window into auditable evidence.

    The indicators are inputs to the analyst layer, not automatic trade orders.
    Conflicting signals intentionally become NEUTRAL so the decision gate can
    return NO_TRADE.
    """
    data = add_quant_trading_indicators(add_basic_indicators(df))
    if data.empty:
        return AnalystEvidence(
            role="technical",
            direction="NEUTRAL",
            confidence=0.0,
            observations=[],
            data_gaps=["No OHLCV rows available."],
            risks=[],
        )

    row = data.iloc[-1]
    bullish = 0
    bearish = 0
    observations: list[str] = []
    risks: list[str] = []

    macd = row.get("macd")
    macd_signal = row.get("macd_signal")
    if pd.notna(macd) and pd.notna(macd_signal):
        if macd > macd_signal:
            bullish += 1
            observations.append("MACD is above its signal line.")
        elif macd < macd_signal:
            bearish += 1
            observations.append("MACD is below its signal line.")

    rsi = row.get("rsi_14")
    if pd.notna(rsi):
        observations.append(f"RSI14={float(rsi):.1f}.")
        if rsi > 55:
            bullish += 1
        elif rsi < 45:
            bearish += 1

    ao = row.get("awesome_oscillator")
    if pd.notna(ao):
        if ao > 0:
            bullish += 1
        elif ao < 0:
            bearish += 1
        observations.append("Awesome Oscillator is positive." if ao > 0 else "Awesome Oscillator is negative.")

    psar = row.get("psar")
    close = row.get("close")
    if pd.notna(psar) and pd.notna(close):
        if close > psar:
            bullish += 1
        elif close < psar:
            bearish += 1
        observations.append("Price is above Parabolic SAR." if close > psar else "Price is below Parabolic SAR.")

    if bool(row.get("shooting_star", False)):
        bearish += 1
        risks.append("Shooting-star candlestick geometry is present.")

    ha_bullish = row.get("ha_bullish")
    if pd.notna(ha_bullish):
        if bool(ha_bullish):
            bullish += 1
        else:
            bearish += 1

    if bullish == bearish:
        direction = "NEUTRAL"
    else:
        direction = "BULLISH" if bullish > bearish else "BEARISH"

    total = bullish + bearish
    confidence = 0.0 if total == 0 else min(0.95, abs(bullish - bearish) / total)

    if bullish and bearish:
        risks.append("Technical indicators are not fully aligned.")

    return AnalystEvidence(
        role="technical",
        direction=direction,
        confidence=confidence,
        observations=observations,
        data_gaps=[],
        risks=risks,
    )
