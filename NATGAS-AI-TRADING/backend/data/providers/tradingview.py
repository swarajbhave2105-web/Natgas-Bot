from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import re
from typing import Any

import httpx
import pandas as pd

from backend.data.continuous import build_continuous_contract
from backend.config import get_active_asset_class
from backend.data.providers.upstox_market_stream import UpstoxMarketStream
from backend.data.providers.upstox_candles import UpstoxCandleProvider
from backend.data.providers.mcx_bhavcopy import load_mcx_bhavcopy


@dataclass(frozen=True)
class TradingViewQuote:
    source: str
    symbol: str
    last_price: float | None
    bid: float | None
    ask: float | None
    volume: float | None
    open_price: float | None
    high_price: float | None
    low_price: float | None
    previous_close: float | None
    change: float | None
    change_percent: float | None
    received_at: datetime | None
    stale: bool
    connected: bool
    realtime: bool | None
    market_closed: bool = False


class TradingViewProvider:
    """TradingView bridge with a public-web fallback.

    The primary source remains the local TradingView bridge. If it has no
    usable quote, the fallback reads the public MCX NATURALGAS page exposed by
    Upstox and combines it with the repo's MCX BhavCopy history for indicators.
    The fallback is intentionally read-only and never places orders.
    """

    PUBLIC_URL = "https://upstox.com/commodity-market-trading/mcx-naturalgas-price/"

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:8787",
        timeout_seconds: float = 8.0,
        upstox_stream: UpstoxMarketStream | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.upstox_stream = upstox_stream

    def get_quote(self) -> TradingViewQuote:
        """Return ONLY the official Upstox V3 WebSocket quote.

        A public Upstox webpage or anonymous TradingView quote must never be
        presented as live market data.
        """
        active_asset = get_active_asset_class()
        symbol = "NSE:NIFTY" if active_asset == "NIFTY" else "MCX:NATURALGAS"
        if not self.upstox_stream:
            return TradingViewQuote(
                source="upstox_ltp_v3",
                symbol=symbol,
                last_price=None, bid=None, ask=None, volume=None,
                open_price=None, high_price=None, low_price=None,
                previous_close=None, change=None, change_percent=None,
                received_at=None, stale=True, connected=False, realtime=False,
            )

        quote = self.upstox_stream.get_quote()
        if quote and quote.get("last_price") is not None and quote.get("connected"):
            market_closed = bool(quote.get("market_closed", False))
            source = str(quote.get("source") or "upstox_ltp_v3")
            received_at = quote.get("received_at")
            if market_closed:
                return TradingViewQuote(
                    source=source,
                    symbol=symbol,
                    last_price=float(quote["last_price"]),
                    bid=quote.get("bid"),
                    ask=quote.get("ask"),
                    volume=quote.get("volume"),
                    open_price=quote.get("open_price"),
                    high_price=quote.get("high_price"),
                    low_price=quote.get("low_price"),
                    previous_close=quote.get("previous_close"),
                    change=quote.get("change"),
                    change_percent=quote.get("change_percent"),
                    received_at=received_at,
                    stale=False,
                    connected=True,
                    realtime=False,
                    market_closed=True,
                )

            age_seconds = (
                (datetime.now(timezone.utc) - received_at).total_seconds()
                if received_at else float("inf")
            )
            # When market is open, treat anything older than 15 seconds as stale.
            fresh = age_seconds <= 15
            return TradingViewQuote(
                source=source,
                symbol=symbol,
                last_price=float(quote["last_price"]) if fresh else None,
                bid=quote.get("bid") if fresh else None,
                ask=quote.get("ask") if fresh else None,
                volume=quote.get("volume") if fresh else None,
                open_price=quote.get("open_price") if fresh else None,
                high_price=quote.get("high_price") if fresh else None,
                low_price=quote.get("low_price") if fresh else None,
                previous_close=quote.get("previous_close") if fresh else None,
                change=quote.get("change") if fresh else None,
                change_percent=quote.get("change_percent") if fresh else None,
                received_at=received_at,
                stale=not fresh,
                connected=fresh,
                realtime=True if fresh else False,
                market_closed=False,
            )

        return TradingViewQuote(
            source="upstox_ltp_v3",
            symbol=symbol,
            last_price=None, bid=None, ask=None, volume=None,
            open_price=None, high_price=None, low_price=None,
            previous_close=None, change=None, change_percent=None,
            received_at=None, stale=True, connected=False, realtime=False,
        )

    def get_upstox_bars(self, timeframe: str = "D", range_: int = 120) -> list[dict[str, float]]:
        """Return genuine Upstox V3 historical candles for MTF analysis."""
        if not self.upstox_stream or not self.upstox_stream.access_token:
            return []
        provider = UpstoxCandleProvider(
            self.upstox_stream.access_token,
            instrument_key=self.upstox_stream.instrument_key or "MCX_FO|570750",
            timeout_seconds=self.timeout_seconds,
        )
        return provider.get_bars(timeframe=timeframe, range_=range_)

    def get_upstox_mtf_diagnostics(self, range_: int = 120) -> dict[str, object]:
        """Fetch MTF candles once and expose counts/errors for dashboard QC."""
        if not self.upstox_stream or not self.upstox_stream.access_token:
            return {"configured": False, "error": "UPSTOX_ACCESS_TOKEN_MISSING"}
        provider = UpstoxCandleProvider(
            self.upstox_stream.access_token,
            instrument_key=self.upstox_stream.instrument_key or "MCX_FO|570750",
            timeout_seconds=self.timeout_seconds,
        )
        counts = {}
        errors = {}
        for timeframe in ("D", "240", "60"):
            bars = provider.get_bars(timeframe=timeframe, range_=max(120, range_))
            counts[timeframe] = len(bars)
            if timeframe in provider.last_errors:
                errors[timeframe] = provider.last_errors[timeframe]
        return {
            "configured": True,
            "instrument_key": provider.instrument_key,
            "counts": counts,
            "errors": errors,
        }

    def get_bars(self, timeframe: str = "D", range_: int = 120) -> list[dict[str, float]]:
        try:
            with httpx.Client(timeout=self.timeout_seconds) as client:
                response = client.get(
                    f"{self.base_url}/bars",
                    params={"timeframe": timeframe, "range": max(20, min(range_, 500))},
                )
                response.raise_for_status()
                payload: dict[str, Any] = response.json()
            bars = self._bars_from_payload(payload)
            if len(bars) >= 50:
                return bars
        except Exception:
            pass

        # The BhavCopy/public fallback is daily-only. Never relabel daily
        # history as 4H or 1H data, because that would corrupt the MTF engine.
        if str(timeframe).upper() in {"D", "1D", "DAY"}:
            return self._public_bars(range_)
        return []

    def _bridge_quote(self, payload: dict[str, Any]) -> TradingViewQuote:
        raw = payload.get("quote") or {}
        received_at_ms = payload.get("last_update_ms")
        received_at = (
            datetime.fromtimestamp(received_at_ms / 1000, tz=timezone.utc)
            if received_at_ms
            else None
        )
        return TradingViewQuote(
            source="tradingview",
            symbol=str(payload.get("symbol") or "MCX:NATURALGAS1!"),
            last_price=_number(raw.get("lp")),
            bid=_number(raw.get("bid")),
            ask=_number(raw.get("ask")),
            volume=_number(raw.get("volume")),
            open_price=_number(raw.get("open_price")),
            high_price=_number(raw.get("high_price")),
            low_price=_number(raw.get("low_price")),
            previous_close=_number(raw.get("prev_close_price")),
            change=_number(raw.get("ch")),
            change_percent=_number(raw.get("chp")),
            received_at=received_at,
            stale=bool(payload.get("stale", True)),
            connected=bool(payload.get("connected", False)),
            realtime=payload.get("realtime"),
        )

    def _bars_from_payload(self, payload: dict[str, Any]) -> list[dict[str, float]]:
        bars = payload.get("bars") or []
        return [
            {
                "time": float(item["time"]),
                "open": float(item["open"]),
                "high": float(item["high"]),
                "low": float(item["low"]),
                "close": float(item["close"]),
                "volume": float(item.get("volume", 0.0)),
            }
            for item in bars
            if all(item.get(key) is not None for key in ("time", "open", "high", "low", "close"))
        ]

    def _public_quote(self) -> TradingViewQuote:
        with httpx.Client(
            timeout=self.timeout_seconds,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) "
                    "AppleWebKit/605.1.15 Version/18.0 Mobile Safari/604.1"
                )
            },
        ) as client:
            response = client.get(self.PUBLIC_URL)
            response.raise_for_status()
            html = response.text

        price = _first_number(html, r"<h2[^>]*>₹([0-9]+(?:\.[0-9]+)?)</h2>")
        change = _signed_first_number(html, r"<span[^>]*>([+-]?)₹([0-9]+(?:\.[0-9]+)?) \(")
        change_percent = _first_number(html, r"₹[0-9]+(?:\.[0-9]+)? \((-?[0-9]+(?:\.[0-9]+)?)%\)")
        open_price = _first_number(html, r"Open<br>₹([0-9]+(?:\.[0-9]+)?)")
        previous_close = _first_number(html, r"Prev\. Close<br>₹([0-9]+(?:\.[0-9]+)?)")
        volume = _first_number(html, r"Volume<br>([0-9,]+)")
        high = _first_number(html, r"Day Range<br>₹[0-9.]+ - ₹([0-9.]+)")
        low = _first_number(html, r"Day Range<br>₹([0-9.]+) - ₹[0-9.]+")
        bid = _first_number(html, r"Best buy price \(₹/ qty\.\)<br>₹([0-9]+(?:\.[0-9]+)?)")
        ask = _first_number(html, r"Best sell price \(₹/ qty\.\)<br>₹([0-9]+(?:\.[0-9]+)?)")

        if price is None:
            raise RuntimeError("PUBLIC_NATGAS_PRICE_NOT_FOUND")

        return TradingViewQuote(
            source="upstox_public",
            symbol="MCX:NATURALGAS",
            last_price=price,
            bid=bid,
            ask=ask,
            volume=volume,
            open_price=open_price,
            high_price=high,
            low_price=low,
            previous_close=previous_close,
            change=change,
            change_percent=change_percent,
            received_at=datetime.now(timezone.utc),
            stale=False,
            connected=True,
            realtime=True,
        )

    def _public_bars(self, range_: int) -> list[dict[str, float]]:
        root = Path("/app")
        files = sorted(root.glob("BhavCopyCommodiyWise_*.xls"))
        frames: list[pd.DataFrame] = []
        for path in files:
            try:
                frames.append(load_mcx_bhavcopy(path))
            except Exception:
                continue
        if not frames:
            raise RuntimeError("MCX_BHAVCOPY_HISTORY_NOT_FOUND")

        data = pd.concat(frames, ignore_index=True)
        continuous = build_continuous_contract(data, roll_days_before_expiry=3, back_adjust=True)
        continuous = continuous.sort_values("timestamp").drop_duplicates("timestamp", keep="last")

        # Overlay today's public quote so the latest daily bar reflects the
        # current contract even before today's BhavCopy is published.
        try:
            quote = self._public_quote()
            if quote.last_price is not None and quote.open_price is not None:
                today = pd.Timestamp.now(tz="Asia/Kolkata").tz_localize(None).normalize()
                row = {
                    "timestamp": today,
                    "continuous_open": quote.open_price,
                    "continuous_high": quote.high_price or quote.last_price,
                    "continuous_low": quote.low_price or quote.last_price,
                    "continuous_close": quote.last_price,
                    "volume": quote.volume or 0.0,
                }
                continuous = pd.concat([continuous, pd.DataFrame([row])], ignore_index=True)
                continuous = continuous.sort_values("timestamp").drop_duplicates(
                    "timestamp", keep="last"
                )
        except Exception:
            pass

        result: list[dict[str, float]] = []
        for _, row in continuous.tail(max(50, min(range_, 500))).iterrows():
            result.append(
                {
                    "time": float(pd.Timestamp(row["timestamp"]).timestamp()),
                    "open": float(row.get("continuous_open", row.get("open"))),
                    "high": float(row.get("continuous_high", row.get("high"))),
                    "low": float(row.get("continuous_low", row.get("low"))),
                    "close": float(row.get("continuous_close", row.get("close"))),
                    "volume": float(row.get("volume", 0.0) or 0.0),
                }
            )
        if len(result) < 50:
            raise RuntimeError("MCX_BHAVCOPY_HISTORY_BELOW_50_BARS")
        return result[-min(range_, len(result)):]


def _number(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _first_number(text: str, pattern: str) -> float | None:
    match = re.search(pattern, text)
    if not match:
        return None
    raw = match.group(1).replace(",", "")
    try:
        return float(raw)
    except ValueError:
        return None


def _signed_first_number(text: str, pattern: str) -> float | None:
    match = re.search(pattern, text)
    if not match:
        return None
    sign = match.group(1)
    raw = match.group(2).replace(",", "")
    try:
        value = float(raw)
    except ValueError:
        return None
    return -value if sign == "-" else value


def quote_to_ohlcv_row(quote: TradingViewQuote) -> dict[str, float] | None:
    if any(value is None for value in (quote.last_price, quote.open_price, quote.high_price, quote.low_price)):
        return None
    return {
        "open": float(quote.open_price),
        "high": float(quote.high_price),
        "low": float(quote.low_price),
        "close": float(quote.last_price),
        "volume": float(quote.volume or 0.0),
    }
