"""Continuous NIFTY live decision loop.

The loop is a read-only monitor. It refreshes the TradingView snapshot and
recomputes the deterministic final decision at a bounded interval. It does not
place orders.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable

from backend.data.providers.tradingview import TradingViewProvider
from backend.nifty.analysts import AnalystEvidence
from backend.nifty.live_final import LiveFinalResult, run_live_final_cycle
from backend.nifty.timeframe import get_nifty_timeframe


@dataclass(frozen=True)
class LoopState:
    running: bool
    cycle_count: int
    last_cycle_at: datetime | None
    last_result: LiveFinalResult | None
    error: str | None


class NiftyLiveLoop:
    def __init__(
        self,
        evidence_factory: Callable[[], list[AnalystEvidence]],
        provider: TradingViewProvider,
        interval_seconds: int = 30,
        timeframe: str = "1H",
        bar_range: int = 120,
    ) -> None:
        self.evidence_factory = evidence_factory
        self.provider = provider
        self.interval_seconds = max(5, interval_seconds)
        self.timeframe = timeframe
        self.bar_range = bar_range
        self._running = False
        self._cycle_count = 0
        self._last_cycle_at: datetime | None = None
        self._last_result: LiveFinalResult | None = None
        self._error: str | None = None

    @property
    def state(self) -> LoopState:
        return LoopState(
            running=self._running,
            cycle_count=self._cycle_count,
            last_cycle_at=self._last_cycle_at,
            last_result=self._last_result,
            error=self._error,
        )

    def run_once(self) -> LiveFinalResult:
        result = run_live_final_cycle(
            self.evidence_factory(),
            provider=self.provider,
            timeframe=get_nifty_timeframe(),
            bar_range=self.bar_range,
        )
        self._cycle_count += 1
        self._last_cycle_at = datetime.now(timezone.utc)
        self._last_result = result
        self._error = None
        return result

    async def run_forever(self) -> None:
        self._running = True
        try:
            while self._running:
                try:
                    self.run_once()
                except Exception as exc:
                    self._error = str(exc)
                await asyncio.sleep(self.interval_seconds)
        finally:
            self._running = False

    def stop(self) -> None:
        self._running = False
