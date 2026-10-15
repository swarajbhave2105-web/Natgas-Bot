"""Live NATGAS multi-timeframe research decision wiring."""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from backend.data.live_snapshot import LiveSnapshotResult, get_live_snapshot
from backend.config import get_active_asset_class
from backend.data.providers.tradingview import TradingViewProvider
from backend.natgas.analysts import AnalystEvidence
from backend.natgas.multi_timeframe import MultiTimeframeAnalysis, analyze_multi_timeframe
from backend.natgas.regime import classify_regime
from backend.natgas.session import is_mcx_session_open
from backend.natgas.signal import NatgasDecision
from backend.natgas.trading_brain import BrainSnapshot, TradingBrain


@dataclass(frozen=True)
class LiveFinalResult:
    snapshot: LiveSnapshotResult
    bars_count: int
    atr: float | None
    regime: str
    technical: AnalystEvidence | None
    decision: object
    multi_timeframe: MultiTimeframeAnalysis | None = None
    brain: BrainSnapshot | None = None
    market_closed: bool = False


def run_live_final_cycle(
    evidence: list[AnalystEvidence],
    provider: TradingViewProvider | None = None,
    timeframe: str = "D",
    bar_range: int = 120,
    brain: TradingBrain | None = None,
) -> LiveFinalResult:
    provider = provider or TradingViewProvider()
    snapshot = get_live_snapshot(provider)
    market_closed = getattr(snapshot, "market_closed", False) or not is_mcx_session_open()

    if not snapshot.usable and not market_closed:
        return LiveFinalResult(
            snapshot, 0, None, "WAITING_FOR_LIVE_FEED", None,
            _no_trade(f"Live Upstox feed unavailable: {snapshot.reason or 'unknown'}"),
            market_closed=False,
        )

    if get_active_asset_class() == "NIFTY":
        # NIFTY is intentionally price-only. Keep the same live loop and
        # decision contract, but do not fetch candles or any extra fields.
        return LiveFinalResult(
            snapshot,
            0,
            None,
            "PRICE_ONLY",
            None,
            _no_trade("NIFTY price-only mode: no technical or extra market data requested."),
            None,
        )

    # MTF analysis must use authenticated Upstox V3 historical candles.
    # Never relabel daily data as 4H/1H and never use public-page data for MTF.
    daily = _frame(_bars(provider, "D", max(120, bar_range)))
    four_hour = _frame(_bars(provider, "240", max(120, bar_range)))
    one_hour = _frame(_bars(provider, "60", max(120, bar_range)))

    # Patterns/triggers are evaluated only on completed candles. The live LTP
    # remains separate and is used as the current price for the decision layer.
    four_hour = _closed_intraday_bars(four_hour, hours=4)
    one_hour = _closed_intraday_bars(one_hour, hours=1)
    daily = _overlay_live_daily(daily, snapshot)

    if min(len(daily), len(four_hour), len(one_hour)) < 50:
        counts = f"1D={len(daily)}, 4H={len(four_hour)}, 1H={len(one_hour)}"
        return LiveFinalResult(
            snapshot,
            min(len(daily), len(four_hour), len(one_hour)),
            None,
            "INSUFFICIENT_MTF_DATA",
            None,
            _no_trade(f"Insufficient multi-timeframe OHLC data ({counts})."),
            market_closed=market_closed,
        )

    mtf = analyze_multi_timeframe(daily, four_hour, one_hour)
    technical = mtf.evidence
    atr = _atr(daily, 14)

    close = float(daily["close"].iloc[-1])
    sma_20 = float(daily["close"].rolling(20).mean().iloc[-1])
    sma_50 = float(daily["close"].rolling(50).mean().iloc[-1])
    regime = classify_regime(close, sma_20, sma_50).regime

    current_price = (
        float(snapshot.quote.last_price)
        if snapshot.quote.last_price is not None
        else close
    )

    # Optional macro/news adapters are not configured in the live service. They
    # are disclosed by the brain as unavailable context, not used as a permanent
    # hard veto against an otherwise validated price-action setup.
    brain_snapshot = (brain or TradingBrain()).evaluate(
        price=current_price,
        atr=atr,
        mtf=mtf,
        data_fresh=not market_closed,
        market_open=not market_closed,
    )
    if market_closed:
        decision = _no_trade("MCX Natural Gas market is closed (regular session: Monday-Friday 09:00-23:30 IST). Entries paused.")
    else:
        decision = _decision_from_brain(brain_snapshot)

    return LiveFinalResult(
        snapshot,
        min(len(daily), len(four_hour), len(one_hour)),
        atr,
        regime,
        technical,
        decision,
        mtf,
        brain_snapshot,
        market_closed=market_closed,
    )


def _frame(raw_bars: list[dict[str, float]]) -> pd.DataFrame:
    return pd.DataFrame(raw_bars)


def _overlay_live_daily(frame: pd.DataFrame, snapshot: LiveSnapshotResult) -> pd.DataFrame:
    if frame.empty:
        return frame

    q = snapshot.quote
    if not all(
        value is not None
        for value in (q.open_price, q.high_price, q.low_price, q.last_price)
    ):
        return frame

    today = pd.Timestamp.now(tz="Asia/Kolkata").normalize()
    today_ts = float(today.timestamp())
    live_row = pd.DataFrame(
        [{
            "time": today_ts,
            "open": float(q.open_price),
            "high": float(q.high_price),
            "low": float(q.low_price),
            "close": float(q.last_price),
            "volume": float(q.volume or 0.0),
        }]
    )
    if "time" in frame.columns:
        frame = frame[frame["time"] < today_ts].copy()
    return pd.concat([frame, live_row], ignore_index=True)


def _closed_intraday_bars(frame: pd.DataFrame, hours: int) -> pd.DataFrame:
    if frame.empty or "time" not in frame.columns:
        return frame
    now_ts = pd.Timestamp.now(tz="UTC").timestamp()
    # Candle timestamps represent the candle start. Retain only candles whose
    # full interval has elapsed; the current forming candle can never trigger.
    return frame[frame["time"] + (hours * 3600) <= now_ts].copy()

def _atr(frame: pd.DataFrame, period: int) -> float | None:
    previous_close = frame["close"].shift(1)
    true_range = pd.concat(
        [
            frame["high"] - frame["low"],
            (frame["high"] - previous_close).abs(),
            (frame["low"] - previous_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    value = true_range.rolling(period).mean().iloc[-1]
    return float(value) if pd.notna(value) and value > 0 else None


def _no_trade(reason: str):
    from backend.natgas.signal import NatgasDecision
    return NatgasDecision(direction="NO_TRADE", confidence=0.0, rationale=[reason])


def _bars(provider: TradingViewProvider, timeframe: str, range_: int) -> list[dict[str, float]]:
    """Use authenticated candles in production while retaining test-provider compatibility."""
    getter = getattr(provider, "get_upstox_bars", None)
    return getter(timeframe=timeframe, range_=range_) if getter else provider.get_bars(timeframe=timeframe, range_=range_)


def _decision_from_brain(brain: BrainSnapshot) -> NatgasDecision:
    is_trigger = brain.state in {"LONG_TRIGGER", "SHORT_TRIGGER"}
    direction = brain.direction if is_trigger and brain.direction else "NO_TRADE"
    rationale = list(brain.reasons) + [brain.blocker]
    return NatgasDecision(
        direction=direction,
        confidence=brain.confidence / 100,
        entry_zone=f"{brain.trigger_level:.2f}" if is_trigger and brain.trigger_level is not None else None,
        invalidation=f"{brain.invalidation:.2f}" if is_trigger and brain.invalidation is not None else None,
        targets=[f"{target:.2f}" for target in brain.targets] if is_trigger else [],
        rationale=rationale,
        risks=list(brain.unavailable_context),
    )
