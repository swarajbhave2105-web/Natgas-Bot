"""Upstox V3 historical candles for NATGAS multi-timeframe research."""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any
from urllib.parse import quote

import httpx


class UpstoxCandleProvider:
    """Read-only historical OHLCV source using Upstox Historical Candle V3."""

    BASE_URL = "https://api.upstox.com/v3/historical-candle"

    def __init__(
        self,
        access_token: str | None,
        instrument_key: str = "MCX_FO|570750",
        timeout_seconds: float = 12.0,
    ) -> None:
        self.access_token = access_token
        self.instrument_key = instrument_key
        self.timeout_seconds = timeout_seconds
        self.last_errors: dict[str, str] = {}
        self.last_counts: dict[str, int] = {}

    def get_bars(self, timeframe: str, range_: int = 120) -> list[dict[str, float]]:
        if not self.access_token:
            return []

        unit, interval = self._map_timeframe(timeframe)
        # Upstox V3 permits up to one quarter for hourly history. Request a
        # little more than needed so exchange holidays/weekends do not leave
        # the research engine short of candles.
        lookback_days = 89 if unit == "hours" else 220
        to_date = datetime.now().date()
        from_date = to_date - timedelta(days=lookback_days)

        encoded_key = quote(self.instrument_key, safe="")
        url = (
            f"{self.BASE_URL}/{encoded_key}/{unit}/{interval}/"
            f"{to_date.isoformat()}/{from_date.isoformat()}"
        )
        try:
            response = httpx.get(
            url,
            headers={
                "Accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
        except Exception as exc:
            self.last_errors[timeframe] = f"{type(exc).__name__}: {exc}"
            self.last_counts[timeframe] = 0
            return []
        payload: dict[str, Any] = response.json()
        candles = ((payload.get("data") or {}).get("candles") or [])

        bars: list[dict[str, float]] = []
        for candle in candles:
            if not isinstance(candle, (list, tuple)) or len(candle) < 5:
                continue
            try:
                timestamp = _timestamp(candle[0])
                bars.append(
                    {
                        "time": timestamp,
                        "open": float(candle[1]),
                        "high": float(candle[2]),
                        "low": float(candle[3]),
                        "close": float(candle[4]),
                        "volume": float(candle[5] or 0.0) if len(candle) > 5 else 0.0,
                    }
                )
            except (TypeError, ValueError, OverflowError):
                continue

        bars.sort(key=lambda row: row["time"])
        result = _dedupe(bars)[-max(50, range_):]
        self.last_errors.pop(timeframe, None)
        self.last_counts[timeframe] = len(result)
        return result

    @staticmethod
    def _map_timeframe(timeframe: str) -> tuple[str, str]:
        normalized = str(timeframe).upper().replace(" ", "")
        if normalized in {"D", "1D", "DAY"}:
            return "days", "1"
        if normalized in {"60", "1H", "H1", "60M"}:
            return "hours", "1"
        if normalized in {"240", "4H", "H4", "240M"}:
            return "hours", "4"
        raise ValueError(f"Unsupported Upstox timeframe: {timeframe}")


def _timestamp(value: Any) -> float:
    if isinstance(value, (int, float)):
        # Upstox examples use ISO timestamps; keep numeric compatibility too.
        return float(value / 1000 if value > 10_000_000_000 else value)
    return datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp()


def _dedupe(bars: list[dict[str, float]]) -> list[dict[str, float]]:
    seen: set[float] = set()
    result: list[dict[str, float]] = []
    for bar in bars:
        key = bar["time"]
        if key in seen:
            continue
        seen.add(key)
        result.append(bar)
    return result
