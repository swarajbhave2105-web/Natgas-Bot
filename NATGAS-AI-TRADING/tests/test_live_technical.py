import pandas as pd

from backend.data.live_snapshot import LiveSnapshotResult
from backend.data.providers.tradingview import TradingViewQuote
from backend.natgas.live_technical import build_live_technical


def test_live_technical_uses_history_plus_live_quote():
    rows = []
    for i in range(80):
        base = 300 + i * 0.4
        rows.append({"open": base, "high": base + 2, "low": base - 1, "close": base + 1, "volume": 1000})
    quote = TradingViewQuote("tradingview", "MCX:NATURALGAS1!", 333.5, None, None, 1000, 332, 335, 330, 334, -0.5, -0.15, None, False, True, True)
    result = build_live_technical(LiveSnapshotResult(quote, True, None), pd.DataFrame(rows))
    assert result.evidence.role == "technical"
    assert result.indicators["rsi_14"] is not None


def test_live_technical_blocks_unusable_snapshot():
    quote = TradingViewQuote("tradingview", "MCX:NATURALGAS1!", 333.5, None, None, None, None, None, None, None, None, None, None, True, True, True)
    result = build_live_technical(LiveSnapshotResult(quote, False, "TRADINGVIEW_DATA_STALE"), pd.DataFrame())
    assert result.evidence.data_gaps == ["TRADINGVIEW_DATA_STALE"]
