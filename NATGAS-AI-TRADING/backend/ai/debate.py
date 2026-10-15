"""Bull/bear debate contract for the NATGAS agent graph."""

from dataclasses import dataclass


@dataclass(frozen=True)
class DebateResult:
    bull_case: list[str]
    bear_case: list[str]
    unresolved: list[str]


def run_debate(
    bull_case: list[str],
    bear_case: list[str],
    *,
    minimum_evidence: int = 2,
) -> DebateResult:
    unresolved = []
    if len(bull_case) < minimum_evidence:
        unresolved.append("Bull case lacks sufficient validated evidence.")
    if len(bear_case) < minimum_evidence:
        unresolved.append("Bear case lacks sufficient validated evidence.")

    overlap = set(bull_case).intersection(bear_case)
    if overlap:
        unresolved.append("At least one observation appears on both sides.")

    return DebateResult(
        bull_case=bull_case,
        bear_case=bear_case,
        unresolved=unresolved,
    )
