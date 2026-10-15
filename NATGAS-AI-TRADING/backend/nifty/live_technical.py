from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from backend.data.live_snapshot import LiveSnapshotResult
from backend.data.providers.tradingview import quote_to_ohlcv_row
from backend.indicators.technical import add_basic_indicators, add_quant_trading_indicators
from backend.nifty.analysts import AnalystEvidence


@dataclass(frozen=True)
class LiveTechnicalResult:
    evidence: AnalystEvidence
    indicators: dict[str, float | bool | None]


def build_live_technical(snapshot: LiveSnapshotResult, history: pd.DataFrame) -> LiveTechnicalResult:
    if not snapshot.usable:
        return LiveTechnicalResult(
            AnalystEvidence(role="technical", direction="NEUTRAL", confidence=0.0,
                            observations=[], data_gaps=[snapshot.reason or "LIVE_SNAPSHOT_UNUSABLE"], risks=[]),
            {},
        )

    row = quote_to_ohlcv_row(snapshot.quote)
    if row is None:
        return LiveTechnicalResult(
            AnalystEvidence(role="technical", direction="NEUTRAL", confidence=0.0,
                            observations=[], data_gaps=["Live quote lacks complete OHLC fields."], risks=[]),
            {},
        )

    columns = ["open", "high", "low", "close", "volume"]
    base = history[columns].copy() if set(columns).issubset(history.columns) else pd.DataFrame(columns=columns)
    data = pd.concat([base, pd.DataFrame([row])], ignore_index=True)
    data = add_quant_trading_indicators(add_basic_indicators(data))
    latest = data.iloc[-1]

    bullish = 0
    bearish = 0
    observations: list[str] = []
    risks: list[str] = []

    for key, label in (("macd_hist", "MACD histogram"), ("awesome_oscillator", "Awesome Oscillator")):
        value = latest.get(key)
        if pd.notna(value):
            observations.append(f"{label}={float(value):.4f}.")
            bullish += int(value > 0)
            bearish += int(value < 0)

    rsi = latest.get("rsi_14")
    if pd.notna(rsi):
        observations.append(f"RSI14={float(rsi):.1f}.")
        bullish += int(rsi > 55)
        bearish += int(rsi < 45)

    close = float(latest["close"])
    psar = latest.get("psar")
    if pd.notna(psar):
        observations.append(f"Price={close:.2f}; PSAR={float(psar):.2f}.")
        bullish += int(close > psar)
        bearish += int(close < psar)

    ha = latest.get("ha_bullish")
    if pd.notna(ha):
        bullish += int(bool(ha))
        bearish += int(not bool(ha))

    if bool(latest.get("shooting_star", False)):
        bearish += 1
        risks.append("Shooting-star geometry is present on the latest observation.")

    direction = "BULLISH" if bullish > bearish else "BEARISH" if bearish > bullish else "NEUTRAL"
    total = bullish + bearish
    confidence = 0.0 if total == 0 else min(0.95, abs(bullish - bearish) / total)

    if bullish and bearish:
        risks.append("Live technical indicators are mixed; decision layer should not force a trade.")

    keys = ["sma_20", "sma_50", "ema_20", "rsi_14", "macd", "macd_signal", "macd_hist",
            "bb_upper", "bb_mid", "bb_lower", "bb_width", "awesome_oscillator", "psar",
            "dual_thrust_upper", "dual_thrust_lower"]
    indicators = {key: (float(latest[key]) if pd.notna(latest[key]) else None) for key in keys}
    indicators["ha_bullish"] = bool(ha) if pd.notna(ha) else None
    indicators["shooting_star"] = bool(latest.get("shooting_star", False))

    return LiveTechnicalResult(
        AnalystEvidence("technical", direction, confidence, observations, [], risks),
        indicators,
    )
