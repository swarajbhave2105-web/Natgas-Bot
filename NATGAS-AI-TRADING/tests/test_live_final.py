"""Tests for TradingView live final wiring."""

from datetime import datetime, timezone

from backend.data.providers.tradingview import TradingViewQuote
from backend.natgas.analysts import AnalystEvidence
from backend.natgas.live_final import run_live_final_cycle


class FakeProvider:
    def get_quote(self):
        return TradingViewQuote(
            source="tradingview",
            symbol="MCX:NATURALGAS1!",
            last_price=300.0,
            bid=299.9,
            ask=300.1,
            volume=1000.0,
            open_price=298.0,
            high_price=303.0,
            low_price=296.0,
            previous_close=297.0,
            change=3.0,
            change_percent=1.0,
            received_at=datetime.now(timezone.utc),
            stale=False,
            connected=True,
            realtime=True,
        )

    def get_bars(self, timeframe="D", range_=120):
        bars = []
        for i in range(80):
            close = 250 + i * 0.65
            bars.append({
                "time": float(i),
                "open": close - 1,
                "high": close + 2,
                "low": close - 2,
                "close": close,
                "volume": 1000,
            })
        return bars


def ev(role, direction):
    return AnalystEvidence(
        role=role,
        direction=direction,
        confidence=0.9,
        observations=[f"{role} evidence"],
        data_gaps=[],
        risks=[],
    )


def test_live_final_cycle_wires_price_atr_and_technical_engine():
    evidence = [
        ev("fundamental", "BULLISH"),
        ev("weather", "BULLISH"),
        ev("macro", "BULLISH"),
        ev("news", "BULLISH"),
        ev("risk", "BULLISH"),
    ]

    result = run_live_final_cycle(evidence, FakeProvider())

    assert result.snapshot.usable
    assert result.bars_count == 80
    assert result.atr is not None
    assert result.technical is not None
    assert result.regime == "BULLISH_TREND"
    # The completed candle is bullish, but the current live price remains
    # below its 1H breakout level: this must stay a watch, not force a trade.
    assert result.decision.direction == "NO_TRADE"
    assert result.brain is not None
    assert result.brain.state in {"WATCH_LONG", "WATCH_SHORT", "NO_TRADE"}
    assert result.brain.invalidation is not None
    assert len(result.brain.targets) == 2
