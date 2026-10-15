"""Data-quality gates used before NATGAS analysis."""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone


@dataclass(frozen=True)
class QuoteForQuality:
    symbol: str
    timestamp: datetime


@dataclass(frozen=True)
class DataQualityResult:
    usable: bool
    reasons: tuple[str, ...]


def validate_quotes(
    quotes: list[QuoteForQuality],
    *,
    required_symbols: set[str],
    max_age_minutes: int | None = None,
    now: datetime | None = None,
) -> DataQualityResult:
    reasons: list[str] = []
    symbols = {q.symbol for q in quotes}
    missing = sorted(required_symbols - symbols)

    if missing:
        reasons.append(f"missing symbols: {', '.join(missing)}")

    if max_age_minutes is not None:
        current = now or datetime.now(timezone.utc)
        cutoff = current - timedelta(minutes=max_age_minutes)
        stale = sorted(q.symbol for q in quotes if q.timestamp < cutoff)
        if stale:
            reasons.append(f"stale quotes: {', '.join(stale)}")

    return DataQualityResult(usable=not reasons, reasons=tuple(reasons))
