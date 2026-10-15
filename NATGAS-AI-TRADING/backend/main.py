"""API entry point for NATGAS AI Trading."""

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pathlib import Path
import os
from datetime import datetime, timezone, timedelta

from backend.broker.upstox import UpstoxBroker
from backend.config import get_active_asset_class, set_active_asset_class, settings
from backend.data.live_snapshot import get_live_snapshot
from backend.data.providers.tradingview import TradingViewProvider
from backend.natgas.live_service import app_lifecycle, loop, upstox_market_stream
from backend.natgas.session import is_mcx_session_open
from backend.nifty.intraday import NiftyIntradayCandleProvider, LOOKBACK_BARS, INSTRUMENT_KEY, is_nse_regular_session_open
from backend.nifty.timeframe import get_nifty_timeframe, set_nifty_timeframe, SUPPORTED_NIFTY_TIMEFRAMES


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    lifespan=app_lifecycle,
)


DASHBOARD_PATH = Path(__file__).resolve().parent / "static" / "index.html"


@app.get("/", include_in_schema=False)
def root() -> FileResponse:
    return FileResponse(DASHBOARD_PATH)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": settings.app_name}


@app.get("/api/v1/asset")
def asset(asset_class: str | None = None) -> dict:
    if asset_class is not None:
        normalized = set_active_asset_class(asset_class)
        upstox_market_stream.set_asset_class(normalized)
    active = get_active_asset_class()
    return {
        "asset_class": active,
        "options": ["NATGAS", "NIFTY"],
        "default": "NATGAS",
    }


@app.get("/api/v1/scope")
def scope() -> dict:
    active = get_active_asset_class()
    if active == "NIFTY":
        return {
            "market": "NSE",
            "instrument": "NIFTY",
            "mode": "research",
            "trade_execution": False,
            "broker": "upstox",
        }
    return {
        "market": "MCX",
        "instrument": "NATGAS",
        "contract_family": ["Natural Gas", "Natural Gas Mini"],
        "mode": "research",
        "trade_execution": False,
        "broker": "upstox",
    }


@app.get("/api/v1/feed/status")
def feed_status() -> dict:
    """Read-only diagnostics; never returns the access token."""
    return upstox_market_stream.status()


@app.get("/api/v1/ai/status")
def ai_status() -> dict:
    """Read-only AI routing and quota status."""
    from backend.ai.model_router import get_active_route_name, get_routes
    from backend.ai.quota_guard import global_quota_guard
    routes = {
        name: {"provider": r.provider, "model": r.model, "base_url": r.base_url}
        for name, r in get_routes().items()
    }
    return {
        "active_route": get_active_route_name(),
        "routes": routes,
        "quota": global_quota_guard.get_status(),
    }



@app.get("/api/v1/live")
def live() -> dict:
    result = get_live_snapshot(
        TradingViewProvider(
            base_url=settings.tradingview_feed_url,
            upstox_stream=upstox_market_stream,
        )
    )

    if get_active_asset_class() == "NIFTY":
        if result.usable:
            return {"status":"LIVE","asset_class":"NIFTY","source":"upstox_ltp_v3","symbol":"NSE:NIFTY","last_price":result.quote.last_price,"received_at":result.quote.received_at.isoformat() if result.quote.received_at else None,"realtime":True,"feed_status":"UPSTOX_LTP_V3","market_closed":False}
        p=NiftyIntradayCandleProvider(upstox_market_stream.access_token)
        bars=p.get_bars("1H",LOOKBACK_BARS["1H"])
        if bars:
            last=bars[-1]
            last_dt=datetime.fromtimestamp(last["time"],tz=timezone.utc).astimezone(timezone(timedelta(hours=5,minutes=30)))
            today_ist=datetime.now(timezone(timedelta(hours=5,minutes=30))).date()
            if (not is_nse_regular_session_open()) or last_dt.date()<today_ist:
                return {"status":"CLOSED_LAST_SESSION","asset_class":"NIFTY","source":"upstox_historical_candle_v3","symbol":"NSE:NIFTY","last_price":last["close"],"received_at":datetime.fromtimestamp(last["time"],tz=timezone.utc).isoformat(),"realtime":False,"feed_status":"LAST_COMPLETED_SESSION","market_closed":True,"session":"NSE_REGULAR_09:15-15:30_IST"}
        diagnostics=upstox_market_stream.status()
        return {"status":"WAITING_FOR_LIVE_FEED","asset_class":"NIFTY","source":"upstox_ltp_v3","symbol":"NSE:NIFTY","last_price":None,"received_at":None,"realtime":False,"feed_status":"DISCONNECTED","reason":result.reason,"instrument_key":diagnostics.get("instrument_key"),"connection_state":diagnostics.get("connection_state"),"upstox_error":diagnostics.get("error"),"market_closed":False}

    if not result.usable:
        diagnostics = upstox_market_stream.status()
        if not is_mcx_session_open():
            last_p = result.quote.last_price or diagnostics.get("last_price")
            return {
                "status": "CLOSED_LAST_SESSION",
                "asset_class": "NATGAS",
                "source": result.quote.source or "upstox_ltp_v3",
                "symbol": result.quote.symbol or "MCX:NATURALGAS",
                "last_price": last_p,
                "received_at": (
                    result.quote.received_at.isoformat()
                    if result.quote.received_at
                    else None
                ),
                "realtime": False,
                "feed_status": "LAST_COMPLETED_SESSION",
                "market_closed": True,
                "session": "MCX_REGULAR_09:00-23:30_IST",
                "reason": "MCX market is closed (regular session: Monday-Friday 09:00-23:30 IST).",
                "instrument_key": diagnostics.get("instrument_key"),
                "connection_state": diagnostics.get("connection_state"),
                "upstox_error": diagnostics.get("error"),
            }
        return {
            "status": "WAITING_FOR_LIVE_FEED",
            "source": "upstox_ltp_v3",
            "symbol": result.quote.symbol,
            "last_price": None,
            "received_at": None,
            "realtime": False,
            "feed_status": "DISCONNECTED",
            "reason": result.reason,
            "upstox_error": diagnostics.get("error"),
            "instrument_key": diagnostics.get("instrument_key"),
            "market_status": diagnostics.get("market_status"),
            "connection_state": diagnostics.get("connection_state"),
            "last_event": diagnostics.get("last_event"),
            "last_event_at": diagnostics.get("last_event_at"),
            "last_message_type": diagnostics.get("last_message_type"),
            "message_count": diagnostics.get("message_count"),
            "tick_count": diagnostics.get("tick_count"),
        }

    return {
        "status": "LIVE",
        "source": result.quote.source,
        "symbol": result.quote.symbol,
        "last_price": result.quote.last_price,
        "bid": result.quote.bid,
        "ask": result.quote.ask,
        "volume": result.quote.volume,
        "open": result.quote.open_price,
        "high": result.quote.high_price,
        "low": result.quote.low_price,
        "previous_close": result.quote.previous_close,
        "change": result.quote.change,
        "change_percent": result.quote.change_percent,
        "received_at": (
            result.quote.received_at.isoformat()
            if result.quote.received_at
            else None
        ),
        "realtime": result.quote.realtime,
        "feed_status": (
            "UPSTOX_LTP_V3"
            if result.quote.source == "upstox_ltp_v3"
            else "UPSTOX_WEBSOCKET"
            if result.quote.source == "upstox_websocket"
            else "UNKNOWN"
        ),
    }


@app.get("/api/v1/mtf/diagnostics")
def mtf_diagnostics() -> dict:
    if get_active_asset_class()=="NIFTY":
        p=NiftyIntradayCandleProvider(upstox_market_stream.access_token)
        for tf in ("1H","15M","5M"): p.get_bars(tf,LOOKBACK_BARS[tf])
        return {"configured":bool(upstox_market_stream.access_token),**p.diagnostics(),"asset_class":"NIFTY","active_timeframe":get_nifty_timeframe()}
    provider=TradingViewProvider(base_url=settings.tradingview_feed_url,upstox_stream=upstox_market_stream)
    return {**provider.get_upstox_mtf_diagnostics(range_=int(os.getenv("NATGAS_LOOP_BAR_RANGE","120"))),"asset_class":"NATGAS"}


@app.get("/api/v1/chart")
def chart(timeframe: str = "60", range_: int = 120) -> dict:
    active=get_active_asset_class()
    if active=="NIFTY":
        aliases={"1H":"1H","60":"1H","15M":"15M","15":"15M","5M":"5M","5":"5M"}
        tf=aliases.get(str(timeframe).upper().replace(" ",""))
        if not tf: raise HTTPException(status_code=400,detail="NIFTY chart timeframe must be 1H, 15M, or 5M.")
        p=NiftyIntradayCandleProvider(upstox_market_stream.access_token)
        bars=p.get_bars(tf,max(LOOKBACK_BARS[tf],min(int(range_),LOOKBACK_BARS[tf])))
        closes=[float(x["close"]) for x in bars]
        sma20=[sum(closes[i-19:i+1])/20 if i>=19 else None for i in range(len(closes))]
        sma50=[sum(closes[i-49:i+1])/50 if i>=49 else None for i in range(len(closes))]
        overlays={"sma20":[{"time":b["time"],"value":sma20[i]} for i,b in enumerate(bars) if sma20[i] is not None],"sma50":[{"time":b["time"],"value":sma50[i]} for i,b in enumerate(bars) if sma50[i] is not None]}
        return {"source":"upstox_historical_candle_v3","asset_class":"NIFTY","instrument_key":INSTRUMENT_KEY,"timeframe":tf,"session":"NSE_REGULAR_09:15-15:30_IST","market_closed":True,"bars":bars,"overlays":overlays}
    normalized=str(timeframe).upper().replace(" ","")
    mapping={"1D":"D","D":"D","4H":"240","240":"240","1H":"60","60":"60"}
    selected=mapping.get(normalized)
    if not selected: raise HTTPException(status_code=400,detail="Unsupported timeframe. Use 1H, 4H, or 1D.")
    safe_range=max(50,min(int(range_),300))
    provider=TradingViewProvider(base_url=settings.tradingview_feed_url,upstox_stream=upstox_market_stream)
    bars=provider.get_upstox_bars(timeframe=selected,range_=safe_range)
    return {"source":"upstox_historical_candle_v3","asset_class":"NATGAS","instrument_key":upstox_market_stream.instrument_key,"timeframe":selected,"bars":bars}


@app.get("/api/v1/live/loop")
def live_loop_status() -> dict:
    state=loop.state; result=state.last_result; active=get_active_asset_class()
    expected_symbol="NSE:NIFTY" if active=="NIFTY" else "MCX:NATURALGAS"
    if result and result.snapshot.quote.symbol!=expected_symbol: result=None
    decision=result.decision if result else None
    if active=="NIFTY" and result and result.multi_timeframe:
        mtf=result.multi_timeframe
        return {"asset_class":"NIFTY","running":state.running,"cycle_count":state.cycle_count,"last_cycle_at":state.last_cycle_at.isoformat() if state.last_cycle_at else None,"error":state.error,"market":"NSE","symbol":"NSE:NIFTY","price":result.snapshot.quote.last_price,"market_closed":result.market_closed,"selected_timeframe":result.selected_timeframe,"regime":result.regime,"atr":result.atr,"decision":decision.model_dump() if decision else None,"multi_timeframe":{"1H":{"bars":mtf.one_hour.bars,"direction":mtf.one_hour.direction,"confidence":mtf.one_hour.confidence,"observations":list(mtf.one_hour.observations)},"15M":{"bars":mtf.fifteen_min.bars,"direction":mtf.fifteen_min.direction,"confidence":mtf.fifteen_min.confidence,"patterns":list(mtf.fifteen_min.patterns),"observations":list(mtf.fifteen_min.observations)},"5M":{"bars":mtf.five_min.bars,"direction":mtf.five_min.direction,"confidence":mtf.five_min.confidence,"trigger":mtf.five_min.trigger,"observations":list(mtf.five_min.observations)}}}
    quote = result.snapshot.quote if result else None
    age_seconds = (datetime.now(timezone.utc) - quote.received_at).total_seconds() if quote and quote.received_at else None
    market_closed = getattr(result, "market_closed", not is_mcx_session_open())
    data_health_status = "MARKET CLOSED" if market_closed else ("LIVE" if age_seconds is not None and age_seconds <= 15 else "DATA DELAY")
    return {
        "asset_class": "NATGAS",
        "running": state.running,
        "cycle_count": state.cycle_count,
        "last_cycle_at": state.last_cycle_at.isoformat() if state.last_cycle_at else None,
        "error": state.error,
        "market": "MCX",
        "symbol": quote.symbol if quote else "MCX:NATURALGAS",
        "price": quote.last_price if quote else None,
        "market_closed": market_closed,
        "regime": result.regime if result else "WAITING_FOR_LIVE_FEED",
        "atr": result.atr if result else None,
        "decision": decision.model_dump() if decision else None,
        "data_health": {
            "status": data_health_status,
            "last_tick_at": quote.received_at.isoformat() if quote and quote.received_at else None,
            "age_seconds": round(age_seconds, 1) if age_seconds is not None else None,
            "price_source": quote.source if quote else "upstox_ltp_v3",
            "connection": "CONNECTED" if quote and quote.connected else "DISCONNECTED",
        },
        "brain": result.brain.payload() if result and result.brain else None,
        "multi_timeframe": (
            {
                "1D": {"bars": result.multi_timeframe.daily.bars, "direction": result.multi_timeframe.daily.direction, "confidence": result.multi_timeframe.daily.confidence, "observations": list(result.multi_timeframe.daily.observations)},
                "4H": {"bars": result.multi_timeframe.four_hour.bars, "direction": result.multi_timeframe.four_hour.direction, "confidence": result.multi_timeframe.four_hour.confidence, "patterns": list(result.multi_timeframe.four_hour.patterns), "observations": list(result.multi_timeframe.four_hour.observations)},
                "1H": {"bars": result.multi_timeframe.one_hour.bars, "direction": result.multi_timeframe.one_hour.direction, "confidence": result.multi_timeframe.one_hour.confidence, "trigger": result.multi_timeframe.one_hour.trigger, "trigger_level": result.multi_timeframe.one_hour.trigger_level, "observations": list(result.multi_timeframe.one_hour.observations)},
            }
            if result and result.multi_timeframe
            else None
        ),
    }

@app.get("/api/v1/nifty/timeframe")
def nifty_timeframe(timeframe: str | None = None) -> dict:
    if get_active_asset_class()!="NIFTY": return {"asset_class":"NATGAS","timeframe":None,"options":[]}
    if timeframe is not None:
        try: set_nifty_timeframe(timeframe)
        except ValueError as exc: raise HTTPException(status_code=400,detail=str(exc))
    return {"asset_class":"NIFTY","timeframe":get_nifty_timeframe(),"options":list(SUPPORTED_NIFTY_TIMEFRAMES)}


@app.get("/api/v1/broker/status")
def broker_status() -> dict:
    broker = UpstoxBroker()
    try:
        return broker.status()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.get("/api/v1/broker/positions")
def broker_positions() -> dict:
    broker = UpstoxBroker()
    try:
        return broker.positions()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
