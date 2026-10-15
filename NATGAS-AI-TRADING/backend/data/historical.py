"""Historical NATGAS data contracts and validation."""

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class HistoricalBar:
    timestamp: datetime
    symbol: str
    open: float
    high: float
    low: float
    close: float
    volume: float | None = None
    open_interest: float | None = None


def validate_bars(bars: list[HistoricalBar]) -> tuple[str, ...]:
    errors: list[str] = []
    previous = None

    for bar in bars:
        if bar.high < max(bar.open, bar.close) or bar.low > min(bar.open, bar.close):
            errors.append(f"invalid OHLC at {bar.timestamp.isoformat()}")
        if bar.low > bar.high:
            errors.append(f"low above high at {bar.timestamp.isoformat()}")
        if previous and bar.timestamp <= previous:
            errors.append("timestamps must be strictly increasing")
        previous = bar.timestamp

    return tuple(errors)
