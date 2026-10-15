"""Background continuous NATGAS loop lifecycle for the FastAPI app."""

from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI

from backend.config import get_active_asset_class, settings
from backend.data.providers.tradingview import TradingViewProvider
from backend.data.providers.upstox_market_stream import UpstoxMarketStream
from backend.natgas.analysts import AnalystEvidence
from backend.natgas.live_loop import NatgasLiveLoop
from backend.nifty.live_loop import NiftyLiveLoop


def _evidence_factory() -> list[AnalystEvidence]:
    return [
        AnalystEvidence(
            role="fundamental",
            direction="NEUTRAL",
            confidence=0.0,
            observations=[],
            data_gaps=["fundamental adapter not configured"],
            risks=[],
        ),
        AnalystEvidence(
            role="weather",
            direction="NEUTRAL",
            confidence=0.0,
            observations=[],
            data_gaps=["weather adapter not configured"],
            risks=[],
        ),
        AnalystEvidence(
            role="macro",
            direction="NEUTRAL",
            confidence=0.0,
            observations=[],
            data_gaps=["macro adapter not configured"],
            risks=[],
        ),
        AnalystEvidence(
            role="news",
            direction="NEUTRAL",
            confidence=0.0,
            observations=[],
            data_gaps=["news adapter not configured"],
            risks=[],
        ),
        AnalystEvidence(
            role="risk",
            direction="NEUTRAL",
            confidence=0.0,
            observations=[],
            data_gaps=["risk adapter not configured"],
            risks=[],
        ),
    ]


_nifty_evidence_factory = _evidence_factory

upstox_market_stream = UpstoxMarketStream(settings.upstox_access_token)

_provider = TradingViewProvider(
    base_url=settings.tradingview_feed_url,
    upstox_stream=upstox_market_stream,
)

_natgas_loop = NatgasLiveLoop(
    evidence_factory=_evidence_factory,
    provider=_provider,
    interval_seconds=int(os.getenv("NATGAS_LOOP_INTERVAL_SECONDS", "30")),
    timeframe=os.getenv("NATGAS_LOOP_TIMEFRAME", "D"),
    bar_range=int(os.getenv("NATGAS_LOOP_BAR_RANGE", "120")),
)

_nifty_loop = NiftyLiveLoop(
    evidence_factory=_nifty_evidence_factory,
    provider=_provider,
    interval_seconds=int(os.getenv("NIFTY_LOOP_INTERVAL_SECONDS", os.getenv("NATGAS_LOOP_INTERVAL_SECONDS", "30"))),
    timeframe=os.getenv("NIFTY_LOOP_TIMEFRAME", "1H"),
    bar_range=int(os.getenv("NIFTY_LOOP_BAR_RANGE", "120")),
)


class AssetLiveLoop:
    """Single scheduler: executes exactly one asset engine at a time."""

    def __init__(self) -> None:
        self._running = False

    @property
    def state(self):
        from dataclasses import replace
        from backend.config import get_active_asset_class
        selected = _nifty_loop.state if get_active_asset_class() == "NIFTY" else _natgas_loop.state
        return replace(selected, running=self._running)

    def run_once(self):
        from backend.config import get_active_asset_class
        return _nifty_loop.run_once() if get_active_asset_class() == "NIFTY" else _natgas_loop.run_once()

    async def run_forever(self):
        self._running = True
        try:
            while self._running:
                try:
                    self.run_once()
                except Exception as exc:
                    # Preserve the existing fail-closed loop behavior.
                    if get_active_asset_class() == "NIFTY":
                        _nifty_loop._error = str(exc)
                    else:
                        _natgas_loop._error = str(exc)
                await asyncio.sleep(
                    _nifty_loop.interval_seconds
                    if get_active_asset_class() == "NIFTY"
                    else _natgas_loop.interval_seconds
                )
        finally:
            self._running = False

    def stop(self):
        self._running = False
        _natgas_loop.stop()
        _nifty_loop.stop()


loop = AssetLiveLoop()
_task: asyncio.Task | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _task
    _task = asyncio.create_task(loop.run_forever())
    yield
    loop.stop()
    if _task:
        await _task


app_lifecycle = lifespan
