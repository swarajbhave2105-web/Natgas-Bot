from __future__ import annotations

from dataclasses import dataclass

from backend.data.live_snapshot import LiveSnapshotResult, get_live_snapshot
from backend.data.providers.tradingview import TradingViewProvider
from backend.nifty.analysts import AnalystEvidence
from backend.nifty.pipeline import PipelineResult, run_pipeline


@dataclass(frozen=True)
class LiveCycleResult:
    snapshot: LiveSnapshotResult
    pipeline: PipelineResult | None


def run_live_cycle(
    evidence: list[AnalystEvidence],
    provider: TradingViewProvider | None = None,
) -> LiveCycleResult:
    snapshot = get_live_snapshot(provider)
    if not snapshot.usable:
        return LiveCycleResult(snapshot=snapshot, pipeline=None)

    return LiveCycleResult(
        snapshot=snapshot,
        pipeline=run_pipeline(evidence),
    )
