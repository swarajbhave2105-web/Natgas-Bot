"""Live NIFTY intraday multi-timeframe research decision wiring."""
from __future__ import annotations
from dataclasses import dataclass
import pandas as pd
from backend.data.live_snapshot import LiveSnapshotResult, get_live_snapshot
from backend.data.providers.tradingview import TradingViewProvider, TradingViewQuote
from backend.nifty.analysts import AnalystEvidence
from backend.nifty.debate import run_debate
from backend.nifty.final_decision import FinalDecisionInput, build_final_decision
from backend.nifty.multi_timeframe import MultiTimeframeAnalysis, analyze_multi_timeframe
from backend.nifty.regime import classify_regime
from backend.nifty.intraday import NiftyIntradayCandleProvider, LOOKBACK_BARS, INSTRUMENT_KEY, is_nse_regular_session_open
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

@dataclass(frozen=True)
class LiveFinalResult:
    snapshot: LiveSnapshotResult
    bars_count: int
    atr: float | None
    regime: str
    technical: AnalystEvidence | None
    decision: object
    multi_timeframe: MultiTimeframeAnalysis | None = None
    market_closed: bool = False
    selected_timeframe: str = "1H"

def run_live_final_cycle(evidence: list[AnalystEvidence], provider: TradingViewProvider | None = None, timeframe: str = "1H", bar_range: int = 120) -> LiveFinalResult:
    provider = provider or TradingViewProvider()
    snapshot = get_live_snapshot(provider)
    candle_provider = NiftyIntradayCandleProvider(provider.upstox_stream.access_token if provider.upstox_stream else None)
    one_hour = _frame(candle_provider.get_bars("1H", max(LOOKBACK_BARS["1H"], bar_range)))
    fifteen = _frame(candle_provider.get_bars("15M", max(LOOKBACK_BARS["15M"], bar_range)))
    five = _frame(candle_provider.get_bars("5M", max(LOOKBACK_BARS["5M"], bar_range)))

    if min(len(one_hour), len(fifteen), len(five)) < 50:
        return LiveFinalResult(snapshot, min(len(one_hour),len(fifteen),len(five)), None, "INSUFFICIENT_INTRADAY_DATA", None, _no_trade("Insufficient completed NIFTY intraday OHLC data."), None, False, timeframe)

    # The engine always uses completed candles. During a closed market, the
    # latest completed session remains the input instead of producing blanks.
    market_closed = not snapshot.usable
    if market_closed:
        last = one_hour.iloc[-1]
        synthetic_quote = TradingViewQuote(
            source="upstox_historical_candle_v3",
            symbol="NSE:NIFTY",
            last_price=float(last["close"]),
            bid=None, ask=None, volume=float(last.get("volume",0.0)),
            open_price=float(last["open"]), high_price=float(last["high"]),
            low_price=float(last["low"]), previous_close=None,
            change=None, change_percent=None,
            received_at=datetime.fromtimestamp(float(last["time"]), tz=timezone.utc),
            stale=False, connected=True, realtime=False,
        )
        snapshot = LiveSnapshotResult(synthetic_quote, True, "MARKET_CLOSED_USING_LAST_COMPLETED_SESSION")

    mtf = analyze_multi_timeframe(one_hour, fifteen, five)
    technical = mtf.evidence
    primary = {"1H": one_hour, "15M": fifteen, "5M": five}.get(timeframe, one_hour)
    atr = _atr(primary, 14)
    close = float(primary["close"].iloc[-1])
    sma_20 = float(primary["close"].rolling(20).mean().iloc[-1])
    sma_50 = float(primary["close"].rolling(50).mean().iloc[-1])
    regime = classify_regime(close, sma_20, sma_50).regime

    merged = _replace_technical(evidence, technical)
    debate = run_debate(merged)
    observations = tuple(obs for item in merged for obs in item.observations)
    risks = tuple(risk for item in merged for risk in item.risks)
    decision = build_final_decision(FinalDecisionInput(
        current_price=float(snapshot.quote.last_price), atr=atr, regime=regime,
        evidence=tuple(merged), debate=debate, catalysts=observations, risks=risks,
    ))
    return LiveFinalResult(snapshot, len(primary), atr, regime, technical, decision, mtf, market_closed, timeframe)

def _frame(raw_bars): return pd.DataFrame(raw_bars)

def _atr(frame: pd.DataFrame, period: int) -> float | None:
    previous_close=frame["close"].shift(1)
    tr=pd.concat([frame["high"]-frame["low"],(frame["high"]-previous_close).abs(),(frame["low"]-previous_close).abs()],axis=1).max(axis=1)
    value=tr.rolling(period).mean().iloc[-1]
    return float(value) if pd.notna(value) and value>0 else None

def _replace_technical(evidence:list[AnalystEvidence], technical:AnalystEvidence)->list[AnalystEvidence]:
    return [item for item in evidence if item.role!="technical"]+[technical]

def _no_trade(reason:str):
    from backend.nifty.signal import NiftyDecision
    return NiftyDecision(direction="NO_TRADE",confidence=0.0,rationale=[reason])
