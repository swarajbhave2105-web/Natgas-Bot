"""MCX market session schedule and state detection for NATGAS."""
from __future__ import annotations

from datetime import datetime, time
from typing import Any
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")
MCX_REGULAR_SESSION = "MCX_REGULAR_09:00-23:30_IST"


def is_mcx_session_open(now: datetime | None = None) -> bool:
    """Return True if the current time falls within MCX trading session.
    
    MCX Natural Gas futures trade Monday through Friday:
    - Normal session: 09:00 to 23:30 IST (standard) or 23:55 IST (DST).
    - Closed on weekends (Saturday, Sunday).
    """
    now = now or datetime.now(IST)
    if now.tzinfo is None:
        now = now.replace(tzinfo=IST)
    else:
        now = now.astimezone(IST)

    # Weekends: Saturday (5) and Sunday (6)
    if now.weekday() >= 5:
        return False

    current_time = now.time()
    return time(9, 0) <= current_time < time(23, 30)


def get_mcx_session_info(now: datetime | None = None) -> dict[str, Any]:
    open_now = is_mcx_session_open(now)
    return {
        "market_closed": not open_now,
        "is_open": open_now,
        "session": MCX_REGULAR_SESSION,
    }
