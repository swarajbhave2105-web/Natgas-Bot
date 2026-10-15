"""Structured NIFTY decision object.

No directional signal is produced here yet. The object exists so every future
agent must return auditable fields and can explicitly choose NO_TRADE.
"""

from typing import Literal

from pydantic import BaseModel, Field


Direction = Literal["LONG", "SHORT", "NO_TRADE"]


class NiftyDecision(BaseModel):
    instrument: str = "NSE_NIFTY"
    direction: Direction = "NO_TRADE"
    confidence: float = Field(default=0, ge=0, le=1)
    entry_zone: str | None = None
    invalidation: str | None = None
    targets: list[str] = []
    rationale: list[str] = []
    catalysts: list[str] = []
    risks: list[str] = []
