"""Strict source-grounded prompts for NATGAS Bull/Bear research."""

from __future__ import annotations

from backend.ai.research_context import ResearchContext

BASE_RULES = """
You are a research agent inside a NATGAS decision-support system.
Use only supplied market evidence and cited research sources.
Never invent prices, storage numbers, weather events, news, sources, or dates.
Distinguish observed facts from interpretation.
State missing evidence explicitly.
Do not place orders or claim certainty or guaranteed returns.
"""


def bull_prompt(context: ResearchContext) -> str:
    return BASE_RULES + """
Build the strongest evidence-based bullish case for MCX Natural Gas.
Challenge weak assumptions and identify what would invalidate the case.
""" + _context(context)


def bear_prompt(context: ResearchContext) -> str:
    return BASE_RULES + """
Build the strongest evidence-based bearish case for MCX Natural Gas.
Challenge weak assumptions and identify what would invalidate the case.
""" + _context(context)


def _context(context: ResearchContext) -> str:
    citations = "\n".join(
        f"[{i}] {source.title} | {source.url}"
        for i, source in enumerate(context.sources, 1)
    )
    evidence = "\n".join(f"- {item}" for item in context.evidence)
    return f"""
Research query:
{context.query}

Market/analyst evidence:
{evidence or "- none supplied"}

Allowed research sources:
{citations or "- none supplied"}
"""
