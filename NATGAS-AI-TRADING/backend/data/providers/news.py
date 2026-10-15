"""News-provider boundary for NATGAS-specific event research."""

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class NewsItem:
    published_at: datetime
    title: str
    source: str
    url: str
    summary: str | None = None


class NewsProvider:
    async def search(self, query: str, limit: int = 20) -> list[NewsItem]:
        raise NotImplementedError
