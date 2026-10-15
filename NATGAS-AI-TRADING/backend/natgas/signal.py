"""Structured NATGAS decision object.

No directional signal is produced here yet. The object exists so every future
agent must return auditable fields and can explicitly choose NO_TRADE.
"""

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


Direction = Literal["LONG", "SHORT", "NO_TRADE"]


class DecisionAction(str, Enum):
    LONG = "LONG"
    SHORT = "SHORT"
    NO_TRADE = "NO_TRADE"


class NatgasDecision(BaseModel):
    instrument: str = "MCX_NATGAS"
    direction: Direction = "NO_TRADE"
    confidence: float = Field(default=0, ge=0, le=1)
    entry_zone: str | None = None
    invalidation: str | None = None
    targets: list[str] = []
    rationale: list[str] = []
    catalysts: list[str] = []
    risks: list[str] = []

    @property
    def action(self) -> DecisionAction:
        """Compatibility alias for legacy pipeline consumers."""
        return DecisionAction(self.direction)
