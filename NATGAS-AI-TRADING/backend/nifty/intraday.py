"""NIFTY-only intraday Upstox V3 candles and NSE session handling."""
from __future__ import annotations

from datetime import datetime, timedelta, time
from typing import Any
from urllib.parse import quote
from zoneinfo import ZoneInfo
import httpx
import pandas as pd

IST = ZoneInfo("Asia/Kolkata")
BASE_URL = "https://api.upstox.com/v3/historical-candle"
INSTRUMENT_KEY = "NSE_INDEX|Nifty 50"

TIMEFRAME_MAP = {
    "1H": ("hours", "1", 3600),
    "15M": ("minutes", "15", 900),
    "5M": ("minutes", "5", 300),
}

# Bar-count windows deliberately stay stable across the three intraday
# timeframes: RSI 14, SMA 20/50, MACD 12/26/9, AO 5/34, and a five-bar
# structure trigger. They are bar-based parameters, not clock-time values.
LOOKBACK_BARS = {"1H": 120, "15M": 240, "5M": 600}

def is_nse_regular_session_open(now: datetime | None = None) -> bool:
    now = now or datetime.now(IST)
    return now.weekday() < 5 and time(9, 15) <= now.time() < time(15, 30)

def _session_filter(rows: list[dict[str, float]], interval_seconds: int) -> list[dict[str, float]]:
    out=[]
    for row in rows:
        dt=datetime.fromtimestamp(float(row["time"]), tz=IST)
        if dt.weekday() >= 5:
            continue
        start=dt.time()
        end=(dt + timedelta(seconds=interval_seconds)).time()
        # Regular NSE equity/index session: 09:15-15:30 IST.
        if start < time(9,15) or start >= time(15,30):
            continue
        if end > time(15,30):
            continue
        out.append(row)
    return out

def _dedupe(rows: list[dict[str,float]]) -> list[dict[str,float]]:
    seen=set(); out=[]
    for row in sorted(rows,key=lambda x:x["time"]):
        key=row["time"]
        if key in seen: continue
        seen.add(key); out.append(row)
    return out

def _validate(rows: list[dict[str,float]], interval_seconds: int) -> tuple[list[dict[str,float]], dict[str,Any]]:
    rows=_dedupe(_session_filter(rows,interval_seconds))
    gaps=[]; duplicates=0; previous=None
    for row in rows:
        if previous is not None:
            delta=int(row["time"]-previous)
            # Gaps across the overnight boundary are expected and ignored.
            a=datetime.fromtimestamp(previous,tz=IST)
            b=datetime.fromtimestamp(row["time"],tz=IST)
            same_day=a.date()==b.date()
            if same_day and delta != interval_seconds:
                gaps.append({"from":previous,"to":row["time"],"delta_seconds":delta})
        previous=row["time"]
    return rows, {"duplicates":duplicates,"intraday_gaps":gaps,"valid":not gaps}

class NiftyIntradayCandleProvider:
    def __init__(self, access_token: str|None, timeout_seconds: float=12.0):
        self.access_token=access_token
        self.timeout_seconds=timeout_seconds
        self.last_errors={}
        self.last_counts={}
        self.last_quality={}

    def get_bars(self, timeframe: str, range_: int|None=None) -> list[dict[str,float]]:
        tf=str(timeframe).upper().replace(" ","")
        if tf in {"60","H1","60M"}: tf="1H"
        elif tf in {"15","15MIN"}: tf="15M"
        elif tf in {"5","5MIN"}: tf="5M"
        if tf not in TIMEFRAME_MAP: raise ValueError(f"Unsupported NIFTY timeframe: {timeframe}")
        if not self.access_token: return []
        unit, interval, seconds=TIMEFRAME_MAP[tf]
        needed=max(LOOKBACK_BARS[tf], int(range_ or LOOKBACK_BARS[tf]))
        # 5/15-minute history is available through the V3 historical API;
        # request enough calendar days to survive weekends/holidays.
        calendar_days=31 if unit=="minutes" else 89
        today=datetime.now(IST).date()
        from_date=today-timedelta(days=calendar_days)
        encoded=quote(INSTRUMENT_KEY,safe="")
        url=f"{BASE_URL}/{encoded}/{unit}/{interval}/{today.isoformat()}/{from_date.isoformat()}"
        try:
            response=httpx.get(url,headers={"Accept":"application/json","Authorization":f"Bearer {self.access_token}"},timeout=self.timeout_seconds)
            response.raise_for_status()
            payload:dict[str,Any]=response.json()
            candles=((payload.get("data") or {}).get("candles") or [])
            rows=[]
            for c in candles:
                if not isinstance(c,(list,tuple)) or len(c)<5: continue
                try:
                    ts=c[0]
                    if isinstance(ts,(int,float)):
                        ts=float(ts/1000 if ts>10_000_000_000 else ts)
                    else:
                        ts=datetime.fromisoformat(str(ts).replace("Z","+00:00")).timestamp()
                    rows.append({"time":float(ts),"open":float(c[1]),"high":float(c[2]),"low":float(c[3]),"close":float(c[4]),"volume":float(c[5] or 0.0) if len(c)>5 else 0.0})
                except (TypeError,ValueError,OverflowError):
                    continue
            rows,quality=_validate(rows,seconds)
            rows=rows[-needed:]
            self.last_counts[tf]=len(rows); self.last_quality[tf]=quality
            self.last_errors.pop(tf,None)
            if len(rows)<50:
                self.last_errors[tf]=f"INSUFFICIENT_BARS:{len(rows)}"
            return rows
        except Exception as exc:
            self.last_counts[tf]=0
            self.last_quality[tf]={"duplicates":0,"intraday_gaps":[],"valid":False}
            self.last_errors[tf]=f"{type(exc).__name__}: {exc}"
            return []

    def diagnostics(self) -> dict[str,Any]:
        return {"instrument_key":INSTRUMENT_KEY,"timeframes":{tf:{"count":self.last_counts.get(tf,0),"errors":self.last_errors.get(tf),"quality":self.last_quality.get(tf,{})} for tf in TIMEFRAME_MAP}}
