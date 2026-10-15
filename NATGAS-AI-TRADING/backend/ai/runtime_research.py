"""Runtime-neutral source-grounded research orchestration.

The caller supplies a configured ResearchProvider (for example the Exa-backed
adapter). This module performs discovery and context assembly only; model calls
remain a separate layer so source retrieval can never silently become a trade.
"""

from __future__ import annotations

from backend.ai.research import ResearchProvider
from backend.ai.research_context import ResearchContext, build_research_context


async def build_context(
    provider: ResearchProvider,
    query: str,
    evidence: list[str] | tuple[str, ...] = (),
    limit: int = 8,
) -> ResearchContext:
    sources = await provider.search(query, limit)
    return build_research_context(query, sources, evidence)
