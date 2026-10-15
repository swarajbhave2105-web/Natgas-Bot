"""Evidence aggregation rules.

The first version intentionally stays deterministic. LLM agents will provide
structured evidence later; this module will combine that evidence without
silently forcing a trade.
"""

from backend.nifty.signal import NiftyDecision


def no_trade(reason: str) -> NiftyDecision:
    return NiftyDecision(
        direction="NO_TRADE",
        confidence=0,
        rationale=[reason],
    )
