"""Build a single auditable feature snapshot from normalized inputs."""

from dataclasses import dataclass


@dataclass(frozen=True)
class FeatureSnapshot:
    mcx_price: float | None
    henry_hub_price: float | None
    usdinr: float | None
    crude_price: float | None
    rsi_14: float | None
    sma_20: float | None
    sma_50: float | None
    storage_surprise: float | None
    heating_demand_signal: float | None
    cooling_demand_signal: float | None
