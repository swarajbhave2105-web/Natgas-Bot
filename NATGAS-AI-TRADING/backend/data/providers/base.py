"""Provider interfaces. Concrete data sources plug into these contracts."""

from abc import ABC, abstractmethod
from datetime import datetime

from backend.data.schemas import OHLCVBar


class MarketDataProvider(ABC):
    @abstractmethod
    async def get_bars(
        self,
        symbol: str,
        timeframe: str,
        start: datetime,
        end: datetime,
    ) -> list[OHLCVBar]:
        raise NotImplementedError
