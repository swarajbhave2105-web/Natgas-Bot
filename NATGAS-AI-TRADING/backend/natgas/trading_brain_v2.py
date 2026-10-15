"""Framework-backed, single-timeframe NATGAS Brain V2.

This module is an isolated decision engine. It emits framework-native Signal
intents and portable DecisionTrace metadata, but does not create orders, call a
broker, or register itself with the framework's execution loop.

Input OHLCV must contain at least 30 completed bars. Column names are accepted
case-insensitively. The last row is treated as the latest completed candle;
live_price, when supplied, is used only as the current entry/trigger price.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Any, Literal

import pandas as pd
from investing_algorithm_framework import (
    DecisionTrace,
    DecisionTraceEntry,
    Signal,
    SignalSide,
    TradingStrategy,
)

Direction = Literal["LONG", "SHORT"]
Action = Literal["NO_TRADE", "WATCH_LONG", "WATCH_SHORT", "LONG_SIGNAL", "SHORT_SIGNAL"]

FRAMEWORK_VERSION = "9.0.0a22"
MINIMUM_RR = 1.8
MINIMUM_BARS = 30


@dataclass(frozen=True)
class BrainV2Config:
    """Risk and signal parameters for the standalone V2 engine."""

    symbol: str = "NATGAS"
    minimum_rr: float = MINIMUM_RR
    minimum_score: int = 60
    breakout_lookback: int = 20
    structure_lookback: int = 5
    atr_period: int = 14
    fast_ema: int = 9
    slow_ema: int = 21
    rsi_period: int = 14
    stop_atr_buffer: float = 0.15
    target1_atr: float = 3.5
    target2_atr: float = 5.0

    def __post_init__(self) -> None:
        if not self.symbol.strip():
            raise ValueError("symbol must be non-empty")
        if not isfinite(self.minimum_rr) or self.minimum_rr < 1.0:
            raise ValueError("minimum_rr must be finite and >= 1.0")
        if not 0 <= self.minimum_score <= 100:
            raise ValueError("minimum_score must be between 0 and 100")
        if self.breakout_lookback < 3 or self.structure_lookback < 3:
            raise ValueError("lookback windows must be at least 3")
        if min(self.atr_period, self.fast_ema, self.slow_ema, self.rsi_period) < 2:
            raise ValueError("indicator periods must be >= 2")
        if self.fast_ema >= self.slow_ema:
            raise ValueError("fast_ema must be less than slow_ema")
        if self.stop_atr_buffer < 0 or self.target1_atr <= 0 or self.target2_atr <= self.target1_atr:
            raise ValueError("invalid ATR stop/target configuration")


class NatgasTradingBrainV2(TradingStrategy):
    """Single-timeframe strategy adapter built on framework-native types.

    The host application should call :meth:`evaluate_frame` during Phase 1.
    :meth:`generate_signals` is provided for framework compatibility only;
    do not register this strategy with an order-executing framework runtime
    until a separate, reviewed paper-only execution adapter exists.
    """

    strategy_id = "natgas_brain_v2"

    def __init__(self, config: BrainV2Config | None = None) -> None:
        self.config = config or BrainV2Config()
        super().__init__(
            algorithm_id="natgas-brain-v2",
            strategy_id=self.strategy_id,
            symbols=[self.config.symbol],
            metadata={
                "engine": "investing-algorithm-framework",
                "framework_version": FRAMEWORK_VERSION,
                "strategy_version": "2.0.0-phase1",
                "execution_mode": "decision_support_only",
                "minimum_rr": self.config.minimum_rr,
            },
        )

    def evaluate_frame(
        self,
        frame: pd.DataFrame,
        live_price: float | None = None,
    ) -> dict[str, Any]:
        """Evaluate one timeframe and return a JSON-serialisable decision."""
        normalized = _normalize_ohlcv(frame)
        if len(normalized) < MINIMUM_BARS:
            return _no_trade(
                "INSUFFICIENT_DATA",
                f"At least {MINIMUM_BARS} completed OHLCV bars are required; received {len(normalized)}.",
                bars=len(normalized),
            )

        if not _valid_ohlcv(normalized):
            return _no_trade(
                "INVALID_DATA",
                "OHLCV contains missing, non-finite, non-positive, or inconsistent prices.",
                bars=len(normalized),
            )

        metrics = _indicators(normalized, self.config)
        if any(not isfinite(float(metrics[k])) for k in ("atr", "ema_fast", "ema_slow", "rsi", "previous_rsi")):
            return _no_trade("INDICATORS_UNAVAILABLE", "Required indicators could not be calculated.", bars=len(normalized))
        if metrics["atr"] <= 0:
            return _no_trade("INVALID_VOLATILITY", "ATR is zero or negative; risk levels cannot be calculated.", bars=len(normalized))

        price = float(live_price) if live_price is not None else float(normalized["close"].iloc[-1])
        if not isfinite(price) or price <= 0:
            return _no_trade("INVALID_LTP", "Live price must be a finite positive number.", bars=len(normalized))

        setup = _classify_setup(normalized, metrics, price, self.config)
        if setup is None:
            return {
                "engine": "investing-algorithm-framework",
                "strategy": self.strategy_id,
                "status": "NO_TRADE",
                "action": "NO_TRADE",
                "direction": None,
                "setup_type": None,
                "confidence_score": 0,
                "confidence_is_probability": False,
                "entry": None,
                "stop_loss": None,
                "target_1": None,
                "target_2": None,
                "risk_reward": None,
                "minimum_rr": self.config.minimum_rr,
                "reasons": ["No qualifying breakout, pullback, or reversal condition on the selected timeframe."],
                "blockers": [],
                "framework_signal": None,
                "decision_trace": _trace("No qualifying setup", metrics, price, None, None, None, None, 0).to_dict(),
                "bars": len(normalized),
            }

        direction: Direction = setup["direction"]
        stop, target1, target2 = _risk_levels(normalized, price, metrics["atr"], direction, self.config)
        risk = price - stop if direction == "LONG" else stop - price
        reward = target1 - price if direction == "LONG" else price - target1
        rr = reward / risk if risk > 0 else 0.0
        score, score_reasons = _score_setup(setup, metrics, rr)
        blockers: list[str] = []
        if risk <= 0:
            blockers.append("The structural stop is on the wrong side of entry.")
        if rr < self.config.minimum_rr:
            blockers.append(f"Target 1 offers {rr:.2f}R, below the configured {self.config.minimum_rr:.2f}R minimum.")
        if score < self.config.minimum_score:
            blockers.append(f"Confluence score {score}/100 is below the configured minimum {self.config.minimum_score}/100.")

        signal = None
        actionable = not blockers
        if actionable:
            side = SignalSide.OPEN_LONG if direction == "LONG" else SignalSide.OPEN_SHORT
            trace = _trace(setup["label"], metrics, price, stop, target1, target2, rr, score, setup=setup["label"])
            signal = Signal(
                symbol=self.config.symbol,
                side=side,
                strength=score / 100.0,
                source=f"natgas_brain_v2:{setup['label']}",
                metadata={
                    "strategy_version": "2.0.0-phase1",
                    "direction": direction,
                    "setup_type": setup["label"],
                    "entry": round(price, 4),
                    "stop_loss": round(stop, 4),
                    "target_1": round(target1, 4),
                    "target_2": round(target2, 4),
                    "risk_reward": round(rr, 4),
                    "confidence_score": score,
                    "confidence_is_probability": False,
                    "execution_mode": "decision_support_only",
                },
            ).with_decision_trace(trace)

        trace = _trace(setup["label"], metrics, price, stop, target1, target2, rr, score, setup=setup["label"])
        return {
            "engine": "investing-algorithm-framework",
            "strategy": self.strategy_id,
            "status": "ACTIONABLE" if actionable else "WATCH",
            "action": ("LONG_SIGNAL" if direction == "LONG" else "SHORT_SIGNAL") if actionable else ("WATCH_LONG" if direction == "LONG" else "WATCH_SHORT"),
            "direction": direction,
            "setup_type": setup["label"],
            "confidence_score": score,
            "confidence_is_probability": False,
            "entry": round(price, 4),
            "stop_loss": round(stop, 4),
            "target_1": round(target1, 4),
            "target_2": round(target2, 4),
            "risk_reward": round(rr, 4),
            "minimum_rr": self.config.minimum_rr,
            "reasons": list(setup["reasons"]) + score_reasons,
            "blockers": blockers,
            "framework_signal": _signal_to_dict(signal),
            "decision_trace": trace.to_dict(),
            "bars": len(normalized),
        }

    def generate_signals(self, context, data) -> list[Signal]:
        """Yield a framework-native signal; this method never places orders."""
        frame = data.get(self.config.symbol)
        if frame is None:
            frame = data.get(f"{self.config.symbol}_ohlcv")
        if not isinstance(frame, pd.DataFrame):
            return []
        result = self.evaluate_frame(frame)
        if result["status"] != "ACTIONABLE":
            return []
        side = SignalSide.OPEN_LONG if result["direction"] == "LONG" else SignalSide.OPEN_SHORT
        trace_entries = [
            DecisionTraceEntry(name="entry", value=float(result["entry"]), unit="MCX price"),
            DecisionTraceEntry(name="stop_loss", value=float(result["stop_loss"]), unit="MCX price"),
            DecisionTraceEntry(name="target_1", value=float(result["target_1"]), unit="MCX price"),
            DecisionTraceEntry(name="target_2", value=float(result["target_2"]), unit="MCX price"),
            DecisionTraceEntry(name="risk_reward", value=float(result["risk_reward"]), unit="R"),
            DecisionTraceEntry(name="confidence_score", value=int(result["confidence_score"]), unit="points"),
        ]
        trace = DecisionTrace(entries=trace_entries, summary=f"{result['direction']} {result['setup_type']}; framework signal only, no order submitted.")
        signal = Signal(
            symbol=self.config.symbol,
            side=side,
            strength=float(result["confidence_score"]) / 100.0,
            source=f"natgas_brain_v2:{result['setup_type']}",
            metadata={
                "entry": result["entry"],
                "stop_loss": result["stop_loss"],
                "target_1": result["target_1"],
                "target_2": result["target_2"],
                "risk_reward": result["risk_reward"],
                "confidence_score": result["confidence_score"],
                "execution_mode": "decision_support_only",
            },
        )
        return [signal.with_decision_trace(trace)]


def _normalize_ohlcv(frame: pd.DataFrame) -> pd.DataFrame:
    if not isinstance(frame, pd.DataFrame):
        raise TypeError("frame must be a pandas DataFrame")
    if frame.empty:
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
    names = {str(column).strip().lower(): column for column in frame.columns}
    missing = [name for name in ("open", "high", "low", "close") if name not in names]
    if missing:
        raise ValueError(f"OHLCV frame is missing required columns: {', '.join(missing)}")
    selected = {
        name: pd.to_numeric(frame[names[name]], errors="coerce")
        for name in ("open", "high", "low", "close")
    }
    selected["volume"] = pd.to_numeric(frame[names["volume"]], errors="coerce") if "volume" in names else pd.Series(0.0, index=frame.index)
    normalized = pd.DataFrame(selected, index=frame.index)
    return normalized.reset_index(drop=True)


def _valid_ohlcv(frame: pd.DataFrame) -> bool:
    values = frame[["open", "high", "low", "close"]]
    if values.isna().any().any() or not values.map(lambda value: isfinite(float(value))).all().all():
        return False
    if (values <= 0).any().any():
        return False
    if (frame["high"] < frame[["open", "close", "low"]].max(axis=1)).any():
        return False
    if (frame["low"] > frame[["open", "close", "high"]].min(axis=1)).any():
        return False
    return True


def _indicators(frame: pd.DataFrame, config: BrainV2Config) -> dict[str, float]:
    close = frame["close"]
    high = frame["high"]
    low = frame["low"]
    previous_close = close.shift(1)
    true_range = pd.concat(
        [high - low, (high - previous_close).abs(), (low - previous_close).abs()],
        axis=1,
    ).max(axis=1)
    atr = true_range.rolling(config.atr_period, min_periods=config.atr_period).mean()
    delta = close.diff()
    gains = delta.clip(lower=0).rolling(config.rsi_period, min_periods=config.rsi_period).mean()
    losses = (-delta.clip(upper=0)).rolling(config.rsi_period, min_periods=config.rsi_period).mean()
    rs = gains / losses.replace(0, float("nan"))
    rsi = 100.0 - (100.0 / (1.0 + rs))
    rsi = rsi.where(losses != 0, 100.0).where(gains != 0, 0.0).fillna(50.0)
    return {
        "atr": float(atr.iloc[-1]),
        "ema_fast": float(close.ewm(span=config.fast_ema, adjust=False).mean().iloc[-1]),
        "ema_slow": float(close.ewm(span=config.slow_ema, adjust=False).mean().iloc[-1]),
        "rsi": float(rsi.iloc[-1]),
        "previous_rsi": float(rsi.iloc[-2]),
        "close": float(close.iloc[-1]),
        "previous_close": float(close.iloc[-2]),
        "high": float(high.iloc[-1]),
        "low": float(low.iloc[-1]),
        "open": float(frame["open"].iloc[-1]),
        "prior20_high": float(high.iloc[-(config.breakout_lookback + 1):-1].max()),
        "prior20_low": float(low.iloc[-(config.breakout_lookback + 1):-1].min()),
        "prior3_high": float(high.iloc[-4:-1].max()),
        "prior3_low": float(low.iloc[-4:-1].min()),
    }


def _classify_setup(frame: pd.DataFrame, m: dict[str, float], price: float, c: BrainV2Config) -> dict[str, Any] | None:
    close, fast, slow, rsi, prev_rsi, atr = m["close"], m["ema_fast"], m["ema_slow"], m["rsi"], m["previous_rsi"], m["atr"]
    bullish_candle = close > m["open"]
    bearish_candle = close < m["open"]

    if price > m["prior20_high"] and close > slow and 52 <= rsi <= 76:
        return {"direction": "LONG", "label": "BREAKOUT_CONTINUATION", "reasons": ["Live price broke above the previous 20 completed bars.", "Completed candle closed above the slow EMA.", "Momentum is positive without exceeding the configured RSI ceiling."]}
    if price < m["prior20_low"] and close < slow and 24 <= rsi <= 48:
        return {"direction": "SHORT", "label": "BREAKDOWN_CONTINUATION", "reasons": ["Live price broke below the previous 20 completed bars.", "Completed candle closed below the slow EMA.", "Momentum is negative without exceeding the configured RSI floor."]}

    if prev_rsi < 35 <= rsi and price > m["prior3_high"]:
        return {"direction": "LONG", "label": "BULLISH_REVERSAL", "reasons": ["RSI recovered above 35 after an oversold reading.", "Price broke above the previous three completed-bar highs."]}
    if prev_rsi > 65 >= rsi and price < m["prior3_low"]:
        return {"direction": "SHORT", "label": "BEARISH_REVERSAL", "reasons": ["RSI fell below 65 after an overbought reading.", "Price broke below the previous three completed-bar lows."]}

    if fast > slow and m["low"] <= fast + 0.25 * atr and price > fast and rsi >= 45 and bullish_candle:
        return {"direction": "LONG", "label": "BULLISH_PULLBACK", "reasons": ["Fast EMA remains above slow EMA.", "Completed candle rejected the fast-EMA area and closed bullish.", "Momentum remains above the neutral zone."]}
    if fast < slow and m["high"] >= fast - 0.25 * atr and price < fast and rsi <= 55 and bearish_candle:
        return {"direction": "SHORT", "label": "BEARISH_PULLBACK", "reasons": ["Fast EMA remains below slow EMA.", "Completed candle rejected the fast-EMA area and closed bearish.", "Momentum remains below the neutral zone."]}
    return None


def _risk_levels(frame: pd.DataFrame, entry: float, atr: float, direction: Direction, c: BrainV2Config) -> tuple[float, float, float]:
    structure = frame.tail(c.structure_lookback)
    if direction == "LONG":
        stop = float(structure["low"].min()) - c.stop_atr_buffer * atr
        return stop, entry + c.target1_atr * atr, entry + c.target2_atr * atr
    stop = float(structure["high"].max()) + c.stop_atr_buffer * atr
    return stop, entry - c.target1_atr * atr, entry - c.target2_atr * atr


def _score_setup(setup: dict[str, Any], m: dict[str, float], rr: float) -> tuple[int, list[str]]:
    score = 50
    reasons = []
    direction = setup["direction"]
    trend_agrees = m["ema_fast"] > m["ema_slow"] if direction == "LONG" else m["ema_fast"] < m["ema_slow"]
    if trend_agrees:
        score += 15
        reasons.append("Fast/slow EMA structure supports the signal (+15).")
    else:
        reasons.append("Fast/slow EMA structure does not support the signal (+0).")
    momentum_agrees = m["rsi"] >= 50 if direction == "LONG" else m["rsi"] <= 50
    if momentum_agrees:
        score += 10
        reasons.append("RSI momentum supports the signal (+10).")
    if rr >= 2.5:
        score += 15
        reasons.append("Target 1 provides at least 2.5R (+15).")
    elif rr >= MINIMUM_RR:
        score += 10
        reasons.append("Target 1 meets the minimum reward-to-risk threshold (+10).")
    else:
        reasons.append("Reward-to-risk is below the configured threshold (+0).")
    if setup["label"].endswith("REVERSAL"):
        score += 5
        reasons.append("Reversal has both an RSI transition and a price-structure break (+5).")
    if setup["label"].endswith("CONTINUATION"):
        score += 5
        reasons.append("Continuation setup has a 20-bar price break (+5).")
    return min(100, score), reasons


def _trace(summary: str, m: dict[str, float], entry: float, stop: float | None, target1: float | None, target2: float | None, rr: float | None, score: int, setup: str | None = None) -> DecisionTrace:
    entries = [
        DecisionTraceEntry("entry", round(float(entry), 4), unit="MCX price", group="risk"),
        DecisionTraceEntry("atr", round(float(m["atr"]), 4), unit="price", group="volatility"),
        DecisionTraceEntry("ema_fast", round(float(m["ema_fast"]), 4), unit="price", group="trend"),
        DecisionTraceEntry("ema_slow", round(float(m["ema_slow"]), 4), unit="price", group="trend"),
        DecisionTraceEntry("rsi", round(float(m["rsi"]), 2), unit="index", group="momentum"),
        DecisionTraceEntry("setup", setup, group="decision"),
        DecisionTraceEntry("confidence_score", int(score), unit="points; not probability", group="decision"),
    ]
    for name, value in (("stop_loss", stop), ("target_1", target1), ("target_2", target2), ("risk_reward", rr)):
        if value is not None and isfinite(float(value)):
            entries.append(DecisionTraceEntry(name, round(float(value), 4), unit="R" if name == "risk_reward" else "MCX price", group="risk"))
    return DecisionTrace(entries=entries, summary=summary)


def _signal_to_dict(signal: Signal | None) -> dict[str, Any] | None:
    if signal is None:
        return None
    return {
        "symbol": signal.symbol,
        "side": signal.side.value,
        "strength": signal.strength,
        "source": signal.source,
        "metadata": dict(signal.metadata),
    }


def _no_trade(reason: str, detail: str, bars: int) -> dict[str, Any]:
    return {
        "engine": "investing-algorithm-framework",
        "strategy": "natgas_brain_v2",
        "status": "NO_TRADE",
        "action": "NO_TRADE",
        "direction": None,
        "setup_type": None,
        "confidence_score": 0,
        "confidence_is_probability": False,
        "entry": None,
        "stop_loss": None,
        "target_1": None,
        "target_2": None,
        "risk_reward": None,
        "minimum_rr": MINIMUM_RR,
        "reasons": [detail],
        "blockers": [reason],
        "framework_signal": None,
        "decision_trace": DecisionTrace(summary=f"NO_TRADE: {reason}. {detail}").to_dict(),
        "bars": bars,
    }
