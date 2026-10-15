"""MCX market-data adapter boundary.

MCX exchange-grade market data is accessed through approved member/vendor
interfaces. This module keeps that integration isolated from the strategy.
"""

from datetime import datetime

from backend.data.providers.base import MarketDataProvider
from backend.data.schemas import OHLCVBar


class MCXProvider(MarketDataProvider):
    """Placeholder for the user's eventual broker/vendor MCX feed."""

    async def get_bars(
        self,
        symbol: str,
        timeframe: str,
        start: datetime,
        end: datetime,
    ) -> list[OHLCVBar]:
        raise NotImplementedError(
            "Connect an approved MCX/broker market-data feed before live use."
        )
