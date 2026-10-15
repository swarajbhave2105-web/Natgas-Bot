"""NIFTY intraday multi-timeframe research intelligence.

Hierarchy:
- 1H: primary trend filter
- 15M: market structure and candlestick confirmation
- 5M: entry trigger

Research-only: this module never places orders.
"""
from __future__ import annotations
from dataclasses import dataclass
import pandas as pd
from backend.nifty.analysts import AnalystEvidence
from backend.nifty.quant_ensemble import build_technical_evidence

@dataclass(frozen=True)
class TimeframeAnalysis:
    timeframe: str
    bars: int
    direction: str
    confidence: float
    observations: tuple[str, ...]
    patterns: tuple[str, ...]
    trigger: str | None

@dataclass(frozen=True)
class MultiTimeframeAnalysis:
    one_hour: TimeframeAnalysis
    fifteen_min: TimeframeAnalysis
    five_min: TimeframeAnalysis
    evidence: AnalystEvidence

def analyze_multi_timeframe(one_hour: pd.DataFrame, fifteen_min: pd.DataFrame, five_min: pd.DataFrame) -> MultiTimeframeAnalysis:
    h1=_base("1H",one_hour)
    m15base=_base("15M",fifteen_min)
    m15patterns=_patterns(fifteen_min,"15M")
    m15direction=_pattern_direction(m15patterns,m15base.direction)
    m15=TimeframeAnalysis("15M",m15base.bars,m15direction,m15base.confidence,m15base.observations,tuple(m15patterns),None)
    m5base=_base("5M",five_min)
    trigger=_entry_trigger(five_min,h1.direction,m15direction)
    m5direction=m5base.direction
    if trigger: m5direction="BULLISH" if trigger.startswith("LONG") else "BEARISH"
    m5=TimeframeAnalysis("5M",m5base.bars,m5direction,m5base.confidence,m5base.observations,(),trigger)
    aligned=h1.direction in {"BULLISH","BEARISH"} and m15direction==h1.direction and trigger is not None and m5direction==h1.direction
    if aligned:
        direction=h1.direction
        confidence=min(0.95,0.40*h1.confidence+0.35*m15base.confidence+0.25*m5base.confidence+0.10)
        observations=[f"1H trend filter: {h1.direction}.",f"15M structure/pattern confirmation: {m15direction}.",f"5M entry trigger confirmed: {trigger}."]
        risks=[]
    else:
        direction="NEUTRAL"; confidence=0.0
        observations=[f"1H trend: {h1.direction}.",f"15M confirmation: {m15direction}.",f"5M trigger: {trigger or 'none'}."]
        risks=["Intraday multi-timeframe hierarchy is not fully aligned; research engine stays NO_TRADE."]
    gaps=[]
    if min(len(one_hour),len(fifteen_min),len(five_min))<50: gaps.append("At least 50 bars are required on every timeframe.")
    evidence=AnalystEvidence(role="technical",direction=direction,confidence=confidence,observations=observations,data_gaps=gaps,risks=risks)
    return MultiTimeframeAnalysis(h1,m15,m5,evidence)

def _base(timeframe:str,frame:pd.DataFrame)->TimeframeAnalysis:
    if len(frame)<50: return TimeframeAnalysis(timeframe,len(frame),"NEUTRAL",0.0,(),(),None)
    technical=build_technical_evidence(frame)
    return TimeframeAnalysis(timeframe,len(frame),technical.direction,float(technical.confidence),tuple(technical.observations),(),None)

def _patterns(frame:pd.DataFrame,label:str)->list[str]:
    if len(frame)<3:return []
    x=frame.tail(3).reset_index(drop=True); prev=x.iloc[-2]; cur=x.iloc[-1]; out=[]
    prev_bear=prev["close"]<prev["open"]; prev_bull=prev["close"]>prev["open"]; cur_bull=cur["close"]>cur["open"]; cur_bear=cur["close"]<cur["open"]
    if cur_bull and prev_bear and cur["open"]<=prev["close"] and cur["close"]>=prev["open"]: out.append("BULLISH_ENGULFING")
    if cur_bear and prev_bull and cur["open"]>=prev["close"] and cur["close"]<=prev["open"]: out.append("BEARISH_ENGULFING")
    if cur["high"]<=prev["high"] and cur["low"]>=prev["low"]: out.append("INSIDE_BAR")
    body=abs(float(cur["close"]-cur["open"])); upper=float(cur["high"]-max(cur["open"],cur["close"])); lower=float(min(cur["open"],cur["close"])-cur["low"])
    if body>0:
        if lower>=body*2 and upper<=body: out.append("BULLISH_REJECTION")
        if upper>=body*2 and lower<=body: out.append("BEARISH_REJECTION")
    prior_high=float(x.iloc[:-1]["high"].max()); prior_low=float(x.iloc[:-1]["low"].min())
    if float(cur["close"])>prior_high: out.append(f"{label}_BREAKOUT_UP")
    elif float(cur["close"])<prior_low: out.append(f"{label}_BREAKOUT_DOWN")
    return out

def _pattern_direction(patterns:list[str],fallback:str)->str:
    bullish=sum(p.startswith("BULLISH") or p.endswith("_BREAKOUT_UP") for p in patterns)
    bearish=sum(p.startswith("BEARISH") or p.endswith("_BREAKOUT_DOWN") for p in patterns)
    if bullish>bearish:return "BULLISH"
    if bearish>bullish:return "BEARISH"
    return fallback

def _entry_trigger(frame:pd.DataFrame,primary_direction:str,confirmation_direction:str)->str|None:
    if len(frame)<6 or primary_direction!=confirmation_direction:return None
    x=frame.tail(6).reset_index(drop=True); cur=x.iloc[-1]; prior=x.iloc[:-1]
    prior_high=float(prior["high"].max()); prior_low=float(prior["low"].min())
    if primary_direction=="BULLISH" and float(cur["close"])>prior_high:return "LONG_5M_CLOSE_ABOVE_PRIOR_5_BAR_HIGH"
    if primary_direction=="BEARISH" and float(cur["close"])<prior_low:return "SHORT_5M_CLOSE_BELOW_PRIOR_5_BAR_LOW"
    return None
