"""Multi-timeframe NATGAS research intelligence.

Hierarchy:
- 1D: primary trend filter
- 4H: market structure and candlestick confirmation
- 1H: entry trigger

Research-only: this module never places orders.
"""
from __future__ import annotations

from dataclasses import dataclass
import pandas as pd

from backend.natgas.analysts import AnalystEvidence
from backend.natgas.quant_ensemble import build_technical_evidence


@dataclass(frozen=True)
class TimeframeAnalysis:
    timeframe: str
    bars: int
    direction: str
    confidence: float
    observations: tuple[str, ...]
    patterns: tuple[str, ...]
    trigger: str | None
    trigger_level: float | None = None
    invalidation_level: float | None = None
    objective_level: float | None = None


@dataclass(frozen=True)
class MultiTimeframeAnalysis:
    daily: TimeframeAnalysis
    four_hour: TimeframeAnalysis
    one_hour: TimeframeAnalysis
    evidence: AnalystEvidence


def analyze_multi_timeframe(
    daily: pd.DataFrame,
    four_hour: pd.DataFrame,
    one_hour: pd.DataFrame,
) -> MultiTimeframeAnalysis:
    d = _base("1D", daily)
    h4 = _base("4H", four_hour)
    h4_patterns = _patterns(four_hour)
    h4_direction = _pattern_direction(h4_patterns, h4.direction)
    h4 = TimeframeAnalysis(
        timeframe="4H",
        bars=h4.bars,
        direction=h4_direction,
        confidence=h4.confidence,
        observations=h4.observations,
        patterns=tuple(h4_patterns),
        trigger=None,
    )

    h1_base = _base("1H", one_hour)
    trigger, trigger_level, invalidation_level, objective_level = _entry_trigger(one_hour, d.direction, h4_direction)
    h1_direction = h1_base.direction
    if trigger:
        h1_direction = "BULLISH" if trigger.startswith("LONG") else "BEARISH"
    h1 = TimeframeAnalysis(
        timeframe="1H",
        bars=h1_base.bars,
        direction=h1_direction,
        confidence=h1_base.confidence,
        observations=h1_base.observations,
        patterns=(),
        trigger=trigger,
        trigger_level=trigger_level,
        invalidation_level=invalidation_level,
        objective_level=objective_level,
    )

    aligned = (
        d.direction in {"BULLISH", "BEARISH"}
        and h4_direction == d.direction
        and trigger is not None
        and h1_direction == d.direction
    )

    if aligned:
        direction = d.direction
        confidence = min(
            0.95,
            0.40 * d.confidence
            + 0.35 * h4.confidence
            + 0.25 * h1_base.confidence
            + 0.10,
        )
        observations = [
            f"1D trend filter: {d.direction}.",
            f"4H structure/pattern confirmation: {h4_direction}.",
            f"1H entry trigger confirmed: {trigger}.",
        ]
        risks = []
    else:
        direction = "NEUTRAL"
        confidence = 0.0
        observations = [
            f"1D trend: {d.direction}.",
            f"4H confirmation: {h4_direction}.",
            f"1H trigger: {trigger or 'none'}.",
        ]
        risks = ["Multi-timeframe hierarchy is not fully aligned; research engine stays NO_TRADE."]

    gaps = []
    if min(len(daily), len(four_hour), len(one_hour)) < 50:
        gaps.append("At least 50 bars are required on every timeframe.")

    evidence = AnalystEvidence(
        role="technical",
        direction=direction,
        confidence=confidence,
        observations=observations,
        data_gaps=gaps,
        risks=risks,
    )
    return MultiTimeframeAnalysis(d, h4, h1, evidence)


def _base(timeframe: str, frame: pd.DataFrame) -> TimeframeAnalysis:
    if len(frame) < 50:
        return TimeframeAnalysis(timeframe, len(frame), "NEUTRAL", 0.0, (), (), None)

    technical = build_technical_evidence(frame)
    return TimeframeAnalysis(
        timeframe=timeframe,
        bars=len(frame),
        direction=technical.direction,
        confidence=float(technical.confidence),
        observations=tuple(technical.observations),
        patterns=(),
        trigger=None,
    )


def _patterns(frame: pd.DataFrame) -> list[str]:
    if len(frame) < 3:
        return []
    x = frame.tail(3).reset_index(drop=True)
    prev = x.iloc[-2]
    cur = x.iloc[-1]
    out: list[str] = []

    prev_bear = prev["close"] < prev["open"]
    prev_bull = prev["close"] > prev["open"]
    cur_bull = cur["close"] > cur["open"]
    cur_bear = cur["close"] < cur["open"]

    if cur_bull and prev_bear and cur["open"] <= prev["close"] and cur["close"] >= prev["open"]:
        out.append("BULLISH_ENGULFING")
    if cur_bear and prev_bull and cur["open"] >= prev["close"] and cur["close"] <= prev["open"]:
        out.append("BEARISH_ENGULFING")

    if cur["high"] <= prev["high"] and cur["low"] >= prev["low"]:
        out.append("INSIDE_BAR")

    body = abs(float(cur["close"] - cur["open"]))
    upper = float(cur["high"] - max(cur["open"], cur["close"]))
    lower = float(min(cur["open"], cur["close"]) - cur["low"])
    if body > 0:
        if lower >= body * 2 and upper <= body:
            out.append("BULLISH_REJECTION")
        if upper >= body * 2 and lower <= body:
            out.append("BEARISH_REJECTION")

    if len(x) >= 3:
        prior_high = float(x.iloc[:-1]["high"].max())
        prior_low = float(x.iloc[:-1]["low"].min())
        if float(cur["close"]) > prior_high:
            out.append("4H_BREAKOUT_UP")
        elif float(cur["close"]) < prior_low:
            out.append("4H_BREAKOUT_DOWN")

    return out


def _pattern_direction(patterns: list[str], fallback: str) -> str:
    bullish = sum(
        p.startswith("BULLISH") or p == "4H_BREAKOUT_UP" for p in patterns
    )
    bearish = sum(
        p.startswith("BEARISH") or p == "4H_BREAKOUT_DOWN" for p in patterns
    )
    if bullish > bearish:
        return "BULLISH"
    if bearish > bullish:
        return "BEARISH"
    return fallback


def _entry_trigger(
    frame: pd.DataFrame,
    daily_direction: str,
    four_hour_direction: str,
) -> tuple[str | None, float | None, float | None, float | None]:
    if len(frame) < 21 or daily_direction != four_hour_direction:
        return None, None, None, None

    x = frame.tail(21).reset_index(drop=True)
    cur = x.iloc[-1]
    prior5 = x.iloc[-6:-1]
    prior20 = x.iloc[:-1]
    prior_high = float(prior5["high"].max())
    prior_low = float(prior5["low"].min())
    range_high = float(prior20["high"].max())
    range_low = float(prior20["low"].min())
    range_size = max(range_high - range_low, 0.0)

    if daily_direction == "BULLISH":
        invalidation = range_low
        objective = range_high + 0.5 * range_size
        trigger = "LONG_1H_CLOSE_ABOVE_PRIOR_5_BAR_HIGH" if float(cur["close"]) > prior_high else None
        return trigger, prior_high, invalidation, objective

    if daily_direction == "BEARISH":
        invalidation = range_high
        objective = range_low - 0.5 * range_size
        trigger = "SHORT_1H_CLOSE_BELOW_PRIOR_5_BAR_LOW" if float(cur["close"]) < prior_low else None
        return trigger, prior_low, invalidation, objective

    return None, None, None, None
