"""Source-grounded research context for NATGAS Bull/Bear agents.

This module deliberately separates source discovery from interpretation. A
configured ResearchProvider supplies citations; the LLM layer consumes only
the returned source records and supplied market evidence.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from backend.ai.research import ResearchSource


@dataclass(frozen=True)
class ResearchContext:
    query: str
    sources: tuple[ResearchSource, ...]
    evidence: tuple[str, ...]


def build_research_context(
    query: str,
    sources: Iterable[ResearchSource],
    evidence: Iterable[str] = (),
) -> ResearchContext:
    validated = tuple(
        source for source in sources
        if source.url and source.title
    )
    return ResearchContext(
        query=query,
        sources=validated,
        evidence=tuple(evidence),
    )


def render_source_citations(context: ResearchContext) -> list[str]:
    return [
        f"[{index}] {source.title} — {source.url}"
        for index, source in enumerate(context.sources, start=1)
    ]
