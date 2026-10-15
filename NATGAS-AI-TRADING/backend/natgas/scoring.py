"""Evidence aggregation rules.

The first version intentionally stays deterministic. LLM agents will provide
structured evidence later; this module will combine that evidence without
silently forcing a trade.
"""

from backend.natgas.signal import NatgasDecision


def no_trade(reason: str) -> NatgasDecision:
    return NatgasDecision(
        direction="NO_TRADE",
        confidence=0,
        rationale=[reason],
    )
