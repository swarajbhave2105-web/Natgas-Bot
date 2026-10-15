"""Exa research adapter contract for the NATGAS desk.

The ChatGPT Exa connector can supply search results during research runs. This
module keeps the application independent of connector internals by accepting a
small async search callable and normalizing its result records.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from backend.ai.research import ResearchProvider, ResearchSource

SearchCallable = Callable[[str, int], Awaitable[list[dict[str, Any]]]]


@dataclass(frozen=True)
class ExaResearchProvider(ResearchProvider):
    """Normalize Exa search records into the desk's source contract."""

    search_callable: SearchCallable

    async def search(self, query: str, limit: int = 10) -> list[ResearchSource]:
        records = await self.search_callable(query, max(1, min(limit, 20)))
        sources: list[ResearchSource] = []
        for item in records:
            url = item.get("url")
            if not url:
                continue
            sources.append(
                ResearchSource(
                    title=item.get("title") or url,
                    url=url,
                    published_at=item.get("publishedDate") or item.get("published_at"),
                    source_type="exa",
                    relevance=item.get("score"),
                )
            )
        return sources
