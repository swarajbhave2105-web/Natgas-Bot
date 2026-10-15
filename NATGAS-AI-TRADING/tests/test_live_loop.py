"""Tests for the continuous NATGAS live loop."""

from datetime import datetime, timezone

from backend.data.providers.tradingview import TradingViewQuote
from backend.natgas.analysts import AnalystEvidence
from backend.natgas.live_loop import NatgasLiveLoop


class FakeProvider:
    def get_quote(self):
        return TradingViewQuote(
            "tradingview", "MCX:NATURALGAS1!", 300, 299.9, 300.1, 1000,
            298, 303, 296, 297, 3, 1,
            datetime.now(timezone.utc), False, True, True
        )

    def get_bars(self, timeframe="D", range_=120):
        return [
            {"time": i, "open": 250+i*.65-1, "high": 250+i*.65+2,
             "low": 250+i*.65-2, "close": 250+i*.65, "volume": 1000}
            for i in range(80)
        ]


def ev(role):
    return AnalystEvidence(role, "BULLISH", 0.9, [f"{role} evidence"], [], [])


def test_loop_runs_and_keeps_latest_decision():
    loop = NatgasLiveLoop(
        evidence_factory=lambda: [
            ev("fundamental"), ev("weather"), ev("macro"),
            ev("news"), ev("risk"),
        ],
        provider=FakeProvider(),
        interval_seconds=5,
    )

    result = loop.run_once()

    assert result.snapshot.usable
    assert loop.state.cycle_count == 1
    assert loop.state.last_cycle_at is not None
    assert loop.state.last_result is result
    assert result.decision.direction == "NO_TRADE"
    assert result.brain is not None
    assert result.brain.state in {"WATCH_LONG", "WATCH_SHORT", "NO_TRADE"}
