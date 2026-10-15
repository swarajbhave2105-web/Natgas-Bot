"""Live/research guardrails for the NIFTY decision service.

No order execution is implemented here. This layer validates freshness,
market session state, data completeness, and whether a decision is allowed.
"""

from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass(frozen=True)
class GuardrailResult:
    allowed: bool
    reasons: tuple[str, ...] = ()


def validate_market_snapshot(
    *,
    last_bar_at: datetime | None,
    required_fields_present: bool,
    max_staleness_minutes: int = 15,
) -> GuardrailResult:
    reasons: list[str] = []

    if last_bar_at is None:
        reasons.append("missing_market_timestamp")
    else:
        if last_bar_at.tzinfo is None:
            last_bar_at = last_bar_at.replace(tzinfo=timezone.utc)
        age_minutes = (datetime.now(timezone.utc) - last_bar_at).total_seconds() / 60
        if age_minutes > max_staleness_minutes:
            reasons.append("market_data_stale")

    if not required_fields_present:
        reasons.append("required_market_fields_missing")

    return GuardrailResult(allowed=not reasons, reasons=tuple(reasons))
