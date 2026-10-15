"""Point-in-time NATGAS market snapshot contracts."""

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class MarketSnapshot:
    as_of: datetime
    symbol: str
    price: float | None
    henry_hub: float | None = None
    usdinr: float | None = None
    crude: float | None = None
    source: str = "research"


def validate_snapshot(snapshot: MarketSnapshot) -> tuple[str, ...]:
    errors: list[str] = []
    if snapshot.price is None:
        errors.append("MCX NATGAS price unavailable")
    if snapshot.price is not None and snapshot.price <= 0:
        errors.append("MCX NATGAS price must be positive")
    if not snapshot.symbol:
        errors.append("symbol is required")
    return tuple(errors)
