from datetime import datetime, timezone

from backend.data.providers.tradingview import TradingViewQuote
from backend.data.live_snapshot import LiveSnapshotResult
from backend.natgas.analysts import AnalystEvidence
from backend.natgas.live_cycle import run_live_cycle


def quote() -> TradingViewQuote:
    return TradingViewQuote(
        source="tradingview",
        symbol="MCX:NATURALGAS1!",
        last_price=334.8,
        bid=None,
        ask=None,
        volume=None,
        open_price=None,
        high_price=None,
        low_price=None,
        previous_close=None,
        change=None,
        change_percent=None,
        received_at=datetime.now(timezone.utc),
        stale=False,
        connected=True,
        realtime=True,
    )


class StubProvider:
    def get_quote(self):
        return quote()


def evidence(role: str) -> AnalystEvidence:
    return AnalystEvidence(
        role=role,
        direction="NEUTRAL",
        confidence=0.5,
        observations=[f"{role} evidence"],
        data_gaps=[],
        risks=[],
    )


def test_live_cycle_blocks_when_feed_is_stale():
    stale = quote().__class__(**{**quote().__dict__, "stale": True})
    class StaleProvider:
        def get_quote(self):
            return stale

    result = run_live_cycle([], StaleProvider())
    assert result.pipeline is None
    assert result.snapshot.reason == "UPSTOX_LIVE_FEED_STALE"


def test_live_cycle_reaches_pipeline_with_usable_feed():
    roles = ["technical", "fundamental", "weather", "macro", "news", "risk"]
    result = run_live_cycle([evidence(role) for role in roles], StubProvider())
    assert result.pipeline is not None
    assert result.pipeline.decision.evidence_count == 6
