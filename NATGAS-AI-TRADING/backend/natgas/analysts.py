"""NATGAS analyst roles and evidence contract."""

from dataclasses import dataclass
from typing import Literal


AnalystRole = Literal[
    "technical",
    "fundamental",
    "weather",
    "macro",
    "news",
    "bull",
    "bear",
    "risk",
]


@dataclass(frozen=True)
class AnalystEvidence:
    role: AnalystRole
    direction: Literal["BULLISH", "BEARISH", "NEUTRAL"]
    confidence: float
    observations: list[str]
    data_gaps: list[str]
    risks: list[str]
