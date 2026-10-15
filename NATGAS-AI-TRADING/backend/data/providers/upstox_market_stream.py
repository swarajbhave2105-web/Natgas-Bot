from __future__ import annotations

import os
import threading
import time
from datetime import datetime, timezone, date
from typing import Any

import httpx
import upstox_client

from backend.config import get_active_asset_class
from backend.natgas.session import is_mcx_session_open


class UpstoxMarketStream:
    """Read-only Upstox V3 market stream for the active MCX NATURALGAS future.

    Uses Upstox's official MarketDataStreamerV3 SDK. No public webpage or
    delayed/anonymous quote is ever exposed as a live price.
    """

    INSTRUMENT_SEARCH_URL = "https://api.upstox.com/v2/instruments/search"
    LTP_V3_URL = "https://api.upstox.com/v3/market-quote/ltp"
    OHLC_V3_URL = "https://api.upstox.com/v3/market-quote/ohlc"

    def __init__(self, access_token: str | None):
        self.access_token = access_token
        self._lock = threading.Lock()
        self._quote: dict[str, Any] | None = None
        self._streamer: Any = None
        self._thread: threading.Thread | None = None
        self._started = False
        self.asset_class = get_active_asset_class()
        self.instrument_key: str | None = self._instrument_for_asset(self.asset_class)
        self.error: str | None = None
        self.connected_at: datetime | None = None
        self.market_status: str | None = None
        self.connection_state = "not_started"
        self.last_event: str | None = None
        self.last_event_at: datetime | None = None
        self.last_message_at: datetime | None = None
        self.last_message_type: str | None = None
        self.subscription_sent = False
        self.message_count = 0
        self.tick_count = 0
        self.last_tick_at: datetime | None = None
        self._ltp_thread: threading.Thread | None = None
        self._ltp_started = False

    def set_asset_class(self, asset_class: str) -> None:
        """Switch the single active market feed; never run both assets together."""
        from backend.config import set_active_asset_class
        normalized = set_active_asset_class(asset_class)
        with self._lock:
            self.asset_class = normalized
            self.instrument_key = self._instrument_for_asset(normalized)
            self._quote = None
            self.connection_state = "switching"
            self.error = None
            self.last_event = "ASSET_SWITCH:" + normalized
            self.last_event_at = datetime.now(timezone.utc)

    @staticmethod
    def _instrument_for_asset(asset_class: str) -> str:
        if asset_class == "NIFTY":
            return "NSE_INDEX|Nifty 50"
        configured = os.getenv("UPSTOX_NATGAS_INSTRUMENT_KEY", "").strip()
        if configured:
            return configured
        return ""

    def start(self) -> None:
        if not self.access_token or self._started:
            return
        self._started = True
        # Use the V3 LTP endpoint as the stable live feed.
        # The direct SDK WebSocket path can repeatedly spawn reconnect threads
        # when the provider returns a 403 handshake, eventually exhausting
        # the Railway process thread budget. The LTP V3 feed is already
        # returning current NATGAS prices with this Analytics Token.
        self._start_ltp_poller()

    def get_quote(self) -> dict[str, Any] | None:
        self.start()
        with self._lock:
            return dict(self._quote) if self._quote else None

    def status(self) -> dict[str, Any]:
        with self._lock:
            quote = dict(self._quote) if self._quote else None
            asset_class = self.asset_class
        return {
            "asset_class": asset_class,
            "configured": bool(self.access_token),
            "started": self._started,
            "connected": self.connection_state in {"connected", "subscribed", "waiting_for_tick", "live"},
            "connection_state": self.connection_state,
            "source": quote.get("source") if quote else "upstox_ltp_v3",
            "instrument_key": self.instrument_key,
            "last_price": quote.get("last_price") if quote else None,
            "received_at": (
                quote.get("received_at").isoformat()
                if quote and quote.get("received_at")
                else None
            ),
            "error": self.error,
            "market_status": self.market_status,
            "connected_at": self.connected_at.isoformat() if self.connected_at else None,
            "last_event": self.last_event,
            "last_event_at": self.last_event_at.isoformat() if self.last_event_at else None,
            "last_message_type": self.last_message_type,
            "last_message_at": self.last_message_at.isoformat() if self.last_message_at else None,
            "subscription_sent": self.subscription_sent,
            "message_count": self.message_count,
            "tick_count": self.tick_count,
            "last_tick_at": self.last_tick_at.isoformat() if self.last_tick_at else None,
        }


    def _start_ltp_poller(self) -> None:
        if not self.access_token or self._ltp_started:
            return
        self._ltp_started = True
        self._ltp_thread = threading.Thread(
            target=self._ltp_poll_loop,
            name="upstox-ltp-v3",
            daemon=True,
        )
        self._ltp_thread.start()

    def _ltp_poll_loop(self) -> None:
        while True:
            try:
                active_asset = get_active_asset_class()
                if active_asset != self.asset_class:
                    with self._lock:
                        self.asset_class = active_asset
                        self.instrument_key = self._instrument_for_asset(active_asset)
                        self._quote = None
                        self.connection_state = "switching"
                if not self.instrument_key:
                    self.instrument_key = self._resolve_instrument_key()
                quote = self._fetch_ltp_v3(self.instrument_key, self.asset_class)
                if quote:
                    with self._lock:
                        websocket_live = bool(
                            self._quote
                            and self._quote.get("source") == "upstox_websocket"
                            and self.last_tick_at
                            and (datetime.now(timezone.utc) - self.last_tick_at).total_seconds() < 5
                        )
                        if not websocket_live:
                            self._quote = quote
                    if not websocket_live:
                        self.connection_state = "live"
                        self.error = None
                        self.last_event = "UPSTOX_LTP_V3_POLL"
                        self.last_event_at = datetime.now(timezone.utc)
            except Exception as exc:
                self.error = f"UPSTOX_LTP_V3_ERROR: {type(exc).__name__}: {exc}"
            time.sleep(1)

    def _fetch_ltp_v3(self, instrument_key: str, asset_class: str) -> dict[str, Any] | None:
        response = httpx.get(
            self.LTP_V3_URL,
            params={"instrument_key": instrument_key},
            headers={
                "Accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
            timeout=8.0,
        )
        response.raise_for_status()
        rows = response.json().get("data") or {}
        row = rows.get(instrument_key) or next(iter(rows.values()), None)
        if not row or row.get("last_price") is None:
            return None

        ltp = float(row["last_price"])
        previous_close = _number(row.get("cp"))

        if asset_class == "NIFTY":
            # NIFTY mode is intentionally price-only. Do not request OHLC,
            # volume, options, fundamentals, or other extra market fields.
            return {
                "source": "upstox_ltp_v3",
                "symbol": "NSE:NIFTY",
                "instrument_key": instrument_key,
                "last_price": ltp,
                "previous_close": None,
                "bid": None,
                "ask": None,
                "volume": None,
                "open_price": None,
                "high_price": None,
                "low_price": None,
                "change": None,
                "change_percent": None,
                "received_at": datetime.now(timezone.utc),
                "realtime": True,
                "stale": False,
                "connected": True,
                "ltq": None,
                "feed_current_ts": None,
            }

        # LTP V3 supplies the current price/volume, while OHLC V3 supplies
        # the current 1-day candle. This keeps the live technical engine
        # populated without falling back to a public webpage.
        open_price = high_price = low_price = None
        volume = _number(row.get("volume"))
        try:
            ohlc_response = httpx.get(
                self.OHLC_V3_URL,
                params={"instrument_key": instrument_key, "interval": "1d"},
                headers={
                    "Accept": "application/json",
                    "Authorization": f"Bearer {self.access_token}",
                },
                timeout=8.0,
            )
            ohlc_response.raise_for_status()
            ohlc_data = ohlc_response.json().get("data") or {}
            ohlc_row = ohlc_data.get(instrument_key) or next(iter(ohlc_data.values()), None)
            if ohlc_row:
                live_ohlc = ohlc_row.get("live_ohlc") or ohlc_row.get("liveOHLC") or {}
                open_price = _number(live_ohlc.get("open"))
                high_price = _number(live_ohlc.get("high"))
                low_price = _number(live_ohlc.get("low"))
                volume = _number(live_ohlc.get("volume")) or volume
        except Exception as exc:
            # LTP remains usable if the auxiliary OHLC request fails.
            self.error = f"UPSTOX_OHLC_V3_WARNING: {type(exc).__name__}: {exc}"

        change = ltp - previous_close if previous_close is not None else None
        change_percent = (
            (change / previous_close) * 100
            if change is not None and previous_close not in (None, 0)
            else None
        )

        ltt_raw = row.get("last_trade_time") or row.get("ltt")
        trade_time = None
        if ltt_raw is not None:
            try:
                if isinstance(ltt_raw, (int, float)):
                    trade_time = datetime.fromtimestamp(
                        float(ltt_raw) / 1000 if float(ltt_raw) > 10_000_000_000 else float(ltt_raw),
                        tz=timezone.utc,
                    )
                else:
                    trade_time = datetime.fromisoformat(str(ltt_raw).replace("Z", "+00:00"))
            except Exception:
                trade_time = None

        market_open = is_mcx_session_open()
        received_at = trade_time or datetime.now(timezone.utc)

        # Distinguish MARKET CLOSED from LIVE MARKET DATA vs STALE/BROKEN DATA
        if not market_open:
            market_closed = True
            realtime = False
            stale = False
            self.market_status = "CLOSED"
        else:
            market_closed = False
            self.market_status = "OPEN"
            age = (datetime.now(timezone.utc) - received_at).total_seconds()
            stale = age > 15
            realtime = not stale

        return {
            "source": "upstox_ltp_v3",
            "symbol": "MCX:NATURALGAS",
            "instrument_key": instrument_key,
            "last_price": ltp,
            "previous_close": previous_close,
            "bid": None,
            "ask": None,
            "volume": volume,
            "open_price": open_price,
            "high_price": high_price,
            "low_price": low_price,
            "change": change,
            "change_percent": change_percent,
            "received_at": received_at,
            "realtime": realtime,
            "stale": stale,
            "connected": True,
            "market_closed": market_closed,
            "ltq": _number(row.get("ltq")),
            "feed_current_ts": None,
        }

    def _run(self) -> None:
        while True:
            try:
                instrument_key = self._resolve_instrument_key()
                self.instrument_key = instrument_key
                self._connect_official_sdk(instrument_key)
            except Exception as exc:
                self.error = f"{type(exc).__name__}: {exc}"
                with self._lock:
                    if self._quote:
                        self._quote["connected"] = False
                print("Upstox V3 WebSocket error:", self.error)
                time.sleep(10)

    def _connect_official_sdk(self, instrument_key: str) -> None:
        self.connection_state = "connecting"
        self.last_event = f"UPSTOX_CONNECTING:{instrument_key}"
        self.last_event_at = datetime.now(timezone.utc)
        configuration = upstox_client.Configuration()
        configuration.access_token = self.access_token

        # Pass the instrument and mode into the official V3 streamer constructor.
        # The SDK queues this initial subscription and sends it as soon as the
        # WebSocket opens, which avoids a race between the open event and a
        # manually-triggered subscribe call.
        streamer = upstox_client.MarketDataStreamerV3(
            upstox_client.ApiClient(configuration),
            [instrument_key],
            "full",
        )
        self._streamer = streamer

        streamer.on("open", self._on_open)
        streamer.on("message", self._on_message)
        streamer.on("error", self._on_error)
        streamer.on("close", self._on_close)
        try:
            streamer.auto_reconnect(True, 5, 0)
        except Exception as exc:
            print("Upstox auto-reconnect configuration skipped:", exc)

        print("Upstox V3 official SDK connecting:", instrument_key)
        streamer.connect()

    def _on_open(self, *_args: Any) -> None:
        self.error = None
        self.connected_at = datetime.now(timezone.utc)
        self.connection_state = "connected"
        self.last_event = "UPSTOX_WEBSOCKET_OPEN"
        self.last_event_at = datetime.now(timezone.utc)
        print("Upstox V3 WebSocket connected:", self.instrument_key)
        try:
            self._streamer.subscribe([self.instrument_key], "full")
            self.subscription_sent = True
            self.connection_state = "waiting_for_tick"
            self.last_event = f"UPSTOX_SUBSCRIBED:{self.instrument_key}:full"
            self.last_event_at = datetime.now(timezone.utc)
            print("Upstox V3 subscribed:", self.instrument_key, "mode=full")
        except Exception as exc:
            self.error = f"UPSTOX_SUBSCRIBE_ERROR: {type(exc).__name__}: {exc}"
            print(self.error)

    def _on_error(self, *args: Any) -> None:
        error = args[-1] if args else "unknown"
        with self._lock:
            ltp_live = bool(
                self._quote
                and self._quote.get("source") == "upstox_ltp_v3"
                and self._quote.get("received_at")
                and (datetime.now(timezone.utc) - self._quote["received_at"]).total_seconds() < 5
            )
        if ltp_live:
            self.connection_state = "live"
            self.error = None
        else:
            self.connection_state = "error"
            self.error = f"UPSTOX_WEBSOCKET_ERROR: {error}"
        self.last_event = "UPSTOX_WEBSOCKET_ERROR"
        self.last_event_at = datetime.now(timezone.utc)
        print(self.error or "Upstox WebSocket error while LTP feed remains live")

    def _on_close(self, *args: Any) -> None:
        code = args[-2] if len(args) >= 2 else None
        message = args[-1] if args else None
        self.connection_state = "closed"
        self.error = f"UPSTOX_MARKET_STREAM_CLOSED: {code} {message}"
        self.last_event = "UPSTOX_MARKET_STREAM_CLOSED"
        self.last_event_at = datetime.now(timezone.utc)
        with self._lock:
            if self._quote:
                self._quote["connected"] = False
        print(self.error)

    def _on_message(self, message: Any) -> None:
        try:
            self.message_count += 1
            self.last_message_at = datetime.now(timezone.utc)
            payload = message if isinstance(message, dict) else {}
            self.last_message_type = str(payload.get("type") or "feed") if isinstance(payload, dict) else type(message).__name__
            if payload.get("type") == "market_info":
                market_info = payload.get("marketInfo") or {}
                segment_status = market_info.get("segmentStatus") or {}
                self.market_status = segment_status.get("MCX_FO")
                return

            feeds = payload.get("feeds") or {}
            feed = feeds.get(self.instrument_key or "")
            if not feed:
                return

            # Upstox V3 full-mode payloads are documented as ff.marketFF;
            # some SDK/message versions expose fullFeed instead. LTPC-only
            # payloads place ltpc directly under feeds[KEY].
            ltpc = feed.get("ltpc") or {}
            ff = feed.get("ff") or {}
            full_feed = feed.get("fullFeed") or feed.get("full_feed") or ff
            market_ff = full_feed.get("marketFF") or full_feed.get("market_ff") or {}
            if market_ff:
                ltpc = market_ff.get("ltpc") or ltpc

            ltp = ltpc.get("ltp")
            if ltp is None:
                return

            ltt = ltpc.get("ltt")
            received_at = (
                datetime.fromtimestamp(int(ltt) / 1000, tz=timezone.utc)
                if ltt
                else datetime.now(timezone.utc)
            )

            ohlc_rows = ((market_ff.get("marketOHLC") or {}).get("ohlc") or [])
            if not ohlc_rows:
                ohlc_rows = ((market_ff.get("market_ohlc") or {}).get("ohlc") or [])
            day_ohlc = next(
                (row for row in ohlc_rows if str(row.get("interval", "")).lower() in {"1d", "day", "d"}),
                None,
            )
            if day_ohlc is None and ohlc_rows:
                day_ohlc = ohlc_rows[-1]

            previous_close = _number(ltpc.get("cp"))
            open_price = _number(day_ohlc.get("open")) if day_ohlc else None
            high_price = _number(day_ohlc.get("high")) if day_ohlc else None
            low_price = _number(day_ohlc.get("low")) if day_ohlc else None
            volume = _number(day_ohlc.get("vol")) if day_ohlc else _number(market_ff.get("vtt"))
            change = float(ltp) - previous_close if previous_close is not None else None
            change_percent = (
                (change / previous_close) * 100
                if change is not None and previous_close not in (None, 0)
                else None
            )

            with self._lock:
                self._quote = {
                    "source": "upstox_websocket",
                    "symbol": "MCX:NATURALGAS",
                    "instrument_key": self.instrument_key,
                    "last_price": float(ltp),
                    "previous_close": previous_close,
                    "bid": None,
                    "ask": None,
                    "volume": volume,
                    "open_price": open_price,
                    "high_price": high_price,
                    "low_price": low_price,
                    "change": change,
                    "change_percent": change_percent,
                    "received_at": received_at,
                    "realtime": True,
                    "stale": False,
                    "connected": True,
                    "feed_current_ts": payload.get("currentTs"),
                }
            self.connection_state = "live"
            self.tick_count += 1
            self.last_tick_at = received_at
            self.last_event = "UPSTOX_LIVE_TICK"
            self.last_event_at = datetime.now(timezone.utc)
            print("Upstox live tick:", ltp, received_at.isoformat())
        except Exception as exc:
            self.error = f"UPSTOX_MESSAGE_ERROR: {exc}"
            print(self.error)

    def _resolve_instrument_key(self) -> str:
        if self.asset_class == "NIFTY":
            return "NSE_INDEX|Nifty 50"

        configured_key = os.getenv("UPSTOX_NATGAS_INSTRUMENT_KEY", "").strip()
        if configured_key:
            print("Using configured NATGAS instrument key:", configured_key)
            return configured_key

        # Upstox's current NATURALGAS MCX contract is exchange token 570750.
        # The canonical instrument key is MCX_FO|570750.
        # Prefer the verified key; Instrument Search is only a fallback.
        verified_key = "MCX_FO|570750"
        try:
            response = httpx.get(
                self.INSTRUMENT_SEARCH_URL,
                params={
                    "query": "NATURALGAS",
                    "exchanges": "MCX",
                    "segments": "FO",
                    "instrument_types": "FUT",
                    "expiry": "current_month",
                    "page_number": 1,
                    "records": 30,
                },
                headers={
                    "Accept": "application/json",
                    "Authorization": f"Bearer {self.access_token}",
                },
                timeout=8.0,
            )
            response.raise_for_status()
            rows = response.json().get("data") or []
            today = date.today()
            candidates: list[tuple[date, str, str]] = []
            for row in rows:
                key = str(row.get("instrument_key") or "").strip()
                exchange = str(row.get("exchange") or "").upper()
                segment = str(row.get("segment") or "").upper()
                instrument_type = str(row.get("instrument_type") or "").upper()
                name = str(row.get("name") or "").upper()
                symbol = str(row.get("trading_symbol") or "").upper()
                underlying = str(row.get("underlying_symbol") or "").upper()
                expiry_raw = row.get("expiry")
                if not key or exchange != "MCX" or (segment and segment != "MCX_FO"):
                    continue
                if instrument_type and instrument_type != "FUT":
                    continue
                if not any("NATURALGAS" in value or "NATURAL GAS" in value for value in (name, symbol, underlying)):
                    continue
                if expiry_raw is None:
                    continue
                try:
                    expiry = date.fromisoformat(str(expiry_raw)[:10])
                except (ValueError, TypeError):
                    continue
                if expiry >= today:
                    candidates.append((expiry, key, symbol))
            if candidates:
                candidates.sort(key=lambda item: item[0])
                expiry, key, symbol = candidates[0]
                print("Resolved active NATGAS contract:", symbol, key, "expiry=", expiry.isoformat())
                return key
        except Exception as exc:
            print("Instrument Search fallback:", type(exc).__name__, exc)

        print("Using verified NATGAS instrument key:", verified_key)
        return verified_key

def _number(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
