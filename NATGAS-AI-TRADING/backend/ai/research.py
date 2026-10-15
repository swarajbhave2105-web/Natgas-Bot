"""Research-source contract.

Exa is used during research/development for source discovery. Production
runtime can use the same contract through a configured search provider.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class ResearchSource:
    title: str
    url: str
    published_at: str | None
    source_type: str
    relevance: float | None = None


class ResearchProvider:
    async def search(self, query: str, limit: int = 10) -> list[ResearchSource]:
        raise NotImplementedError
