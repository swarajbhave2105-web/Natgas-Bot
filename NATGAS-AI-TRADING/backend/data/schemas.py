"""Canonical market-data schemas used by every provider adapter."""

from datetime import datetime
from pydantic import BaseModel, Field


class OHLCVBar(BaseModel):
    timestamp: datetime
    symbol: str
    timeframe: str
    open: float
    high: float
    low: float
    close: float
    volume: float | None = None
    open_interest: float | None = None


class FundamentalSnapshot(BaseModel):
    as_of: datetime
    henry_hub_price: float | None = None
    storage_surprise: float | None = None
    production_signal: float | None = None
    demand_signal: float | None = None
    lng_signal: float | None = None


class WeatherSnapshot(BaseModel):
    as_of: datetime
    region: str
    temperature_anomaly: float | None = None
    heating_demand_signal: float | None = None
    cooling_demand_signal: float | None = None
    source: str
