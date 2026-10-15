"""NIFTY-only intraday timeframe state.

The NATGAS timeframe model is untouched. NIFTY runs one intraday hierarchy:
1H primary trend -> 15m confirmation -> 5m trigger.
"""
from __future__ import annotations
import threading

SUPPORTED_NIFTY_TIMEFRAMES = ("1H", "15M", "5M")
_lock = threading.Lock()
_active = "1H"

def get_nifty_timeframe() -> str:
    with _lock:
        return _active

def set_nifty_timeframe(value: str) -> str:
    normalized = str(value).strip().upper().replace(" ", "")
    aliases = {"60":"1H","1H":"1H","H1":"1H","15":"15M","15M":"15M","15MIN":"15M","5":"5M","5M":"5M","5MIN":"5M"}
    normalized = aliases.get(normalized, normalized)
    if normalized not in SUPPORTED_NIFTY_TIMEFRAMES:
        raise ValueError("NIFTY timeframe must be 1H, 15M, or 5M.")
    global _active
    with _lock:
        _active = normalized
        return _active
