"""Application configuration for the NATGAS research engine."""

from dataclasses import dataclass
import os
import threading


@dataclass(frozen=True)
class Settings:
    app_name: str = "NATGAS AI Trading"
    environment: str = os.getenv("ENVIRONMENT", "development")
    eia_api_key: str | None = os.getenv("EIA_API_KEY")
    tradingview_feed_url: str = os.getenv(
        "TRADINGVIEW_FEED_URL", "http://127.0.0.1:8787"
    )
    # Analytics tokens are valid for 1 year and support read-only market data.
    # Prefer the standard token when present, otherwise use the analytics token.
    upstox_analytics_token: str | None = os.getenv("UPSTOX_ANALYTICS_TOKEN")
    upstox_access_token: str | None = os.getenv("UPSTOX_ACCESS_TOKEN") or upstox_analytics_token
    upstox_live_order_enabled: bool = (
        os.getenv("UPSTOX_LIVE_ORDER_ENABLED", "false").lower() == "true"
    )
    timezone: str = "Asia/Kolkata"
    # Exactly two supported asset classes. NATGAS remains the default.
    asset_class: str = os.getenv("ASSET_CLASS", "NATGAS").strip().upper()


settings = Settings()

_SUPPORTED_ASSETS = {"NATGAS", "NIFTY"}
_asset_lock = threading.Lock()
_active_asset_class = settings.asset_class if settings.asset_class in _SUPPORTED_ASSETS else "NATGAS"


def get_active_asset_class() -> str:
    with _asset_lock:
        return _active_asset_class


def set_active_asset_class(asset_class: str) -> str:
    normalized = str(asset_class).strip().upper()
    if normalized not in _SUPPORTED_ASSETS:
        raise ValueError("Asset class must be NATGAS or NIFTY.")
    global _active_asset_class
    with _asset_lock:
        _active_asset_class = normalized
        return _active_asset_class
