from __future__ import annotations

from dataclasses import dataclass

from backend.data.providers.tradingview import TradingViewProvider, TradingViewQuote


@dataclass(frozen=True)
class LiveSnapshotResult:
    quote: TradingViewQuote
    usable: bool
    reason: str | None
    market_closed: bool = False


def get_live_snapshot(provider: TradingViewProvider | None = None) -> LiveSnapshotResult:
    provider = provider or TradingViewProvider()
    quote = provider.get_quote()

    if not quote.connected:
        return LiveSnapshotResult(quote, False, "UPSTOX_LIVE_FEED_DISCONNECTED")

    if getattr(quote, "market_closed", False):
        return LiveSnapshotResult(quote, False, "MCX_MARKET_CLOSED", market_closed=True)

    if quote.stale:
        return LiveSnapshotResult(quote, False, "UPSTOX_LIVE_FEED_STALE")

    if quote.last_price is None:
        return LiveSnapshotResult(quote, False, "UPSTOX_LIVE_PRICE_MISSING")

    if quote.realtime is False:
        return LiveSnapshotResult(quote, False, "UPSTOX_FEED_NOT_REALTIME")

    return LiveSnapshotResult(quote, True, None, market_closed=False)
