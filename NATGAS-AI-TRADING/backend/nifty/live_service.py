"""Background continuous NIFTY loop lifecycle for the FastAPI app."""

from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI

from backend.config import settings
from backend.data.providers.tradingview import TradingViewProvider
from backend.data.providers.upstox_market_stream import UpstoxMarketStream
from backend.nifty.analysts import AnalystEvidence
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


upstox_market_stream = UpstoxMarketStream(settings.upstox_access_token)

loop = NiftyLiveLoop(
    evidence_factory=_evidence_factory,
    provider=TradingViewProvider(
        base_url=settings.tradingview_feed_url,
        upstox_stream=upstox_market_stream,
    ),
    interval_seconds=int(os.getenv("NIFTY_LOOP_INTERVAL_SECONDS", "30")),
    timeframe=os.getenv("NIFTY_LOOP_TIMEFRAME", "D"),
    bar_range=int(os.getenv("NIFTY_LOOP_BAR_RANGE", "120")),
)
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
