"""Connect LLM Bull/Bear research into the NIFTY evidence pipeline."""

from __future__ import annotations

from backend.ai.bull_bear_runner import BullBearResearch
from backend.nifty.analysts import AnalystEvidence


def research_to_evidence(research: BullBearResearch) -> list[AnalystEvidence]:
    """Convert model outputs into auditable analyst evidence.

    Model text is preserved as an observation but is never treated as verified
    market data. Source count is exposed so downstream logic can reject empty
    research runs.
    """
    return [
        AnalystEvidence(
            role="bull",
            direction="BULLISH",
            confidence=0.5 if research.bull.source_count else 0.0,
            observations=[
                research.bull.text or "Bull agent returned no analysis.",
                f"Research sources supplied: {research.bull.source_count}.",
            ],
            data_gaps=[] if research.bull.source_count else ["No research sources supplied."],
            risks=["LLM interpretation requires validation against deterministic market evidence."],
        ),
        AnalystEvidence(
            role="bear",
            direction="BEARISH",
            confidence=0.5 if research.bear.source_count else 0.0,
            observations=[
                research.bear.text or "Bear agent returned no analysis.",
                f"Research sources supplied: {research.bear.source_count}.",
            ],
            data_gaps=[] if research.bear.source_count else ["No research sources supplied."],
            risks=["LLM interpretation requires validation against deterministic market evidence."],
        ),
    ]
