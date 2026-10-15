from datetime import datetime, timezone

from backend.data.live_snapshot import LiveSnapshotResult
from backend.data.providers.tradingview import TradingViewQuote


def test_live_snapshot_result_rejects_stale_feed():
    quote = TradingViewQuote(
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
        stale=True,
        connected=True,
        realtime=True,
    )

    result = LiveSnapshotResult(quote, False, "TRADINGVIEW_DATA_STALE")

    assert not result.usable
    assert result.reason == "TRADINGVIEW_DATA_STALE"
