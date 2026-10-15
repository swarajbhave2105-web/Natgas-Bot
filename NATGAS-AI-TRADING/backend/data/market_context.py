"""External NATGAS market-driver adapters: EIA storage, NOAA weather, macro and news."""
from __future__ import annotations

import re
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import httpx


@dataclass
class MarketContext:
    fundamental: dict[str, Any]
    weather: dict[str, Any]
    macro: dict[str, Any]
    news: dict[str, Any]
    fetched_at: str
    errors: list[str]


_CACHE: tuple[float, MarketContext] | None = None
TTL_SECONDS = 600.0


def get_market_context() -> MarketContext:
    global _CACHE
    now = time.time()
    if _CACHE and now - _CACHE[0] < TTL_SECONDS:
        return _CACHE[1]

    errors: list[str] = []
    fundamental = _eia_storage(errors)
    weather = _noaa_weather(errors)
    macro = _macro(errors)
    news = _news(errors)
    context = MarketContext(
        fundamental=fundamental,
        weather=weather,
        macro=macro,
        news=news,
        fetched_at=datetime.now(timezone.utc).isoformat(),
        errors=errors,
    )
    _CACHE = (now, context)
    return context


def _eia_storage(errors: list[str]) -> dict[str, Any]:
    """Use EIA's published weekly storage table; no secret required."""
    url = "https://www.eia.gov/dnav/ng/NG_STOR_WKLY_S1_W.htm"
    try:
        html = httpx.get(url, timeout=10, headers={"User-Agent": "NATGAS-AI-TRADING/1.0"}).text
        match = re.search(r"Total Lower 48 States\s*</?[^>]*>.*?([0-9,]+)", html, re.I | re.S)
        if not match:
            # The page can change its markup; extract the first visible table row instead.
            match = re.search(r"Total Lower 48 States.*?([0-9,]+)", html, re.I | re.S)
        if not match:
            raise RuntimeError("EIA storage value not found")
        current = float(match.group(1).replace(",", ""))
        # Capture nearby weekly numeric values for a simple recent trend.
        block = html[match.start():match.start() + 3000]
        values = [float(x.replace(",", "")) for x in re.findall(r">([0-9]{3,4}(?:,[0-9]{3})?)<", block)]
        values = values[:8]
        direction = "BULLISH" if len(values) >= 2 and values[-1] < values[-2] else "BEARISH" if len(values) >= 2 and values[-1] > values[-2] else "NEUTRAL"
        observation = f"EIA Lower-48 working gas storage: {current:,.0f} Bcf."
        if len(values) >= 2:
            delta = values[-1] - values[-2]
            observation += f" Latest weekly change proxy: {delta:+,.0f} Bcf."
        return {"status": "OK", "direction": direction, "confidence": 0.65 if direction != "NEUTRAL" else 0.0, "observations": [observation], "source": url}
    except Exception as exc:
        errors.append(f"fundamental: {type(exc).__name__}: {exc}")
        return {"status": "ERROR", "direction": "NEUTRAL", "confidence": 0.0, "observations": [], "error": str(exc)}


def _noaa_weather(errors: list[str]) -> dict[str, Any]:
    """Sample NOAA 7-day forecasts in major U.S. gas-demand/supply regions."""
    points = {"Louisiana": (30.45, -91.19), "Texas": (29.76, -95.37), "New York": (40.71, -74.01), "Illinois": (41.88, -87.63)}
    temps: list[float] = []
    observations: list[str] = []
    headers = {"User-Agent": "NATGAS-AI-TRADING/1.0 contact=research@example.com"}
    for name, (lat, lon) in points.items():
        try:
            p = httpx.get(f"https://api.weather.gov/points/{lat},{lon}", headers=headers, timeout=8).json()
            hourly = p["properties"]["forecastHourly"]
            data = httpx.get(hourly, headers=headers, timeout=8).json()
            periods = data["properties"]["periods"][:48]
            vals = [float(x["temperature"]) for x in periods if isinstance(x.get("temperature"), (int, float))]
            if vals:
                avg = sum(vals) / len(vals)
                temps.append(avg)
                observations.append(f"{name}: 48h forecast average {avg:.1f}°F.")
        except Exception as exc:
            errors.append(f"weather {name}: {type(exc).__name__}: {exc}")
    if not temps:
        return {"status": "ERROR", "direction": "NEUTRAL", "confidence": 0.0, "observations": []}
    avg = sum(temps) / len(temps)
    # Temperature extremes are a demand-risk flag, not a claim of direction.
    direction = "BULLISH" if avg <= 45 or avg >= 82 else "NEUTRAL"
    confidence = 0.45 if direction != "NEUTRAL" else 0.0
    observations.append(f"Regional 48h average across sampled locations: {avg:.1f}°F.")
    return {"status": "OK", "direction": direction, "confidence": confidence, "observations": observations, "source": "NOAA/NWS"}


def _macro(errors: list[str]) -> dict[str, Any]:
    """Read-only market proxies from Yahoo chart API: DXY and WTI."""
    observations: list[str] = []
    directions: list[str] = []
    for symbol, label in [("DX-Y.NYB", "DXY"), ("CL=F", "WTI")]:
        try:
            url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?range=5d&interval=1d"
            payload = httpx.get(url, timeout=8, headers={"User-Agent": "Mozilla/5.0"}).json()
            closes = [x for x in payload["chart"]["result"][0]["indicators"]["quote"][0]["close"] if x is not None]
            if len(closes) >= 2:
                pct = (closes[-1] / closes[-2] - 1) * 100
                observations.append(f"{label}: {closes[-1]:.2f} ({pct:+.2f}% vs prior close).")
                # Stronger dollar is a headwind; stronger oil is a cross-commodity support signal.
                directions.append("BEARISH" if label == "DXY" and pct > 0.25 else "BULLISH" if label == "DXY" and pct < -0.25 else "BULLISH" if label == "WTI" and pct > 0.75 else "BEARISH" if label == "WTI" and pct < -0.75 else "NEUTRAL")
        except Exception as exc:
            errors.append(f"macro {label}: {type(exc).__name__}: {exc}")
    non_neutral = [d for d in directions if d != "NEUTRAL"]
    direction = non_neutral[0] if non_neutral and all(d == non_neutral[0] for d in non_neutral) else "NEUTRAL"
    return {"status": "OK" if observations else "ERROR", "direction": direction, "confidence": 0.35 if direction != "NEUTRAL" else 0.0, "observations": observations, "source": "Yahoo Finance market data"}


def _news(errors: list[str]) -> dict[str, Any]:
    """Use Google News RSS for current NATGAS headlines; no article body is stored."""
    url = "https://news.google.com/rss/search?q=natural+gas+Henry+Hub&hl=en-US&gl=US&ceid=US:en"
    try:
        root = ET.fromstring(httpx.get(url, timeout=10, headers={"User-Agent": "NATGAS-AI-TRADING/1.0"}).text)
        titles = [x.text.strip() for x in root.findall(".//item/title") if x.text][:8]
        bull = sum(len(re.findall(r"bull|surge|rise|higher|cold|freeze|demand", t, re.I)) for t in titles)
        bear = sum(len(re.findall(r"drop|fall|lower|warm|mild|oversupply|production", t, re.I)) for t in titles)
        direction = "BULLISH" if bull > bear + 1 else "BEARISH" if bear > bull + 1 else "NEUTRAL"
        return {"status": "OK", "direction": direction, "confidence": 0.25 if direction != "NEUTRAL" else 0.0, "observations": titles[:5], "source": url}
    except Exception as exc:
        errors.append(f"news: {type(exc).__name__}: {exc}")
        return {"status": "ERROR", "direction": "NEUTRAL", "confidence": 0.0, "observations": [], "error": str(exc)}
