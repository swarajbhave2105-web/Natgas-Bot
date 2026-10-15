"""Production-grade explainable NATGAS Trading Brain decision engine.

Quantitative Architecture:
DATA QUALITY & HYGIENE
  ↓
MARKET REGIME ENGINE (Expansion, Pullback, Range, Squeeze, High-Vol, Exhaustion)
  ↓
MULTI-TIMEFRAME STRUCTURE (1D HTF Trend → 4H MTF Structure → 1H LTF Trigger)
  ↓
TIME-FRAME ALIGNMENT (STRONG, PARTIAL, MIXED, CONFLICT, NO_TRADE)
  ↓
ORTHOGONAL CONFLUENCE SCORING (0-100% across Alignment, Regime, RR, Trigger, Distance)
  ↓
STRICT STRUCTURAL RISK/REWARD (Mandatory ≥1.8R to TP1)
  ↓
FALSE-POSITIVE & OVEREXTENSION GUARDRAILS
  ↓
EXPLAINABLE STATE MACHINE (NO_TRADE, WATCH, TRIGGER, COOLDOWN)

Strictly research/analysis only: Never submits broker orders.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Literal

from backend.natgas.multi_timeframe import MultiTimeframeAnalysis

BrainState = Literal[
    "NO_TRADE",
    "WATCH_LONG",
    "WATCH_SHORT",
    "LONG_TRIGGER",
    "SHORT_TRIGGER",
    "COOLDOWN",
]


class MarketRegime:
    TRENDING_EXPANSION = "TRENDING_EXPANSION"
    TRENDING_PULLBACK = "TRENDING_PULLBACK"
    RANGE_CONSOLIDATION = "RANGE_CONSOLIDATION"
    COMPRESSION_SQUEEZE = "COMPRESSION_SQUEEZE"
    HIGH_VOLATILITY = "HIGH_VOLATILITY"
    EXHAUSTION_REVERSAL = "EXHAUSTION_REVERSAL"
    NORMAL = "NORMAL"


class TimeframeAlignment:
    STRONG_ALIGNMENT = "STRONG_ALIGNMENT"
    PARTIAL_ALIGNMENT = "PARTIAL_ALIGNMENT"
    MIXED = "MIXED"
    CONFLICT = "CONFLICT"
    NO_TRADE = "NO_TRADE"


@dataclass(frozen=True)
class BrainEvent:
    at: str
    event: str
    confidence: int
    detail: str


@dataclass
class PaperSignal:
    direction: str
    entry: float
    stop: float
    target1: float
    target2: float
    confidence: int
    opened_at: str
    mfe: float = 0.0
    mae: float = 0.0
    outcome: str = "OPEN"
    closed_at: str | None = None
    trailing_stop: float | None = None
    r_multiple: float = 0.0
    setup_type: str = "BREAKOUT_EXPANSION"


@dataclass(frozen=True)
class BrainSnapshot:
    state: BrainState
    setup: str
    direction: str | None
    confidence: int
    trend: str
    structure: str
    momentum: str
    volatility: str
    breakout: str
    confirmation: str
    risk_reward: str
    blocker: str
    next_trigger: str | None
    trigger_level: float | None
    invalidation: float | None
    targets: tuple[float, float] | tuple[()]
    reasons: tuple[str, ...]
    unavailable_context: tuple[str, ...]
    evaluation_count: int
    rejected_count: int
    last_evaluated_at: str
    events: tuple[BrainEvent, ...]
    paper_signals: tuple[PaperSignal, ...]
    regime: str = MarketRegime.NORMAL
    alignment: str = TimeframeAlignment.MIXED
    confluence_score: int = 0
    risk_reward_ratio: float = 0.0
    setup_type: str = "BREAKOUT_EXPANSION"

    def payload(self) -> dict:
        result = asdict(self)
        result["events"] = [asdict(event) for event in self.events]
        result["paper_signals"] = [asdict(signal) for signal in self.paper_signals]
        result["targets"] = list(self.targets)
        result["reasons"] = list(self.reasons)
        result["unavailable_context"] = list(self.unavailable_context)
        return result


@dataclass
class TradingBrain:
    """Maintains setup progression, multi-timeframe confluence, and paper validation."""

    cooldown_cycles: int = 3
    evaluation_count: int = 0
    rejected_count: int = 0
    current_state: BrainState = "NO_TRADE"
    _cooldown_remaining: int = 0
    _events: list[BrainEvent] = field(default_factory=list)
    _paper: list[PaperSignal] = field(default_factory=list)

    def evaluate(
        self,
        *,
        price: float,
        atr: float | None,
        mtf: MultiTimeframeAnalysis | None,
        data_fresh: bool,
        market_open: bool = True,
        now: datetime | None = None,
    ) -> BrainSnapshot:
        now = now or datetime.now(timezone.utc)
        stamp = now.isoformat()
        self.evaluation_count += 1
        self._update_paper(price, now)

        # 1. DATA QUALITY & INTEGRITY GATE
        if (not data_fresh and market_open) or price <= 0 or atr is None or atr <= 0 or mtf is None:
            self.rejected_count += 1
            return self._snapshot(
                state="NO_TRADE",
                setup="Insufficient confirmation",
                direction=None,
                confidence=0,
                trend="DATA UNAVAILABLE",
                structure="DATA UNAVAILABLE",
                momentum="DATA UNAVAILABLE",
                volatility="DATA UNAVAILABLE",
                breakout="DATA UNAVAILABLE",
                confirmation="NONE",
                risk_reward="NOT EVALUATED",
                blocker="Live price, ATR, or multi-timeframe candles are unavailable.",
                reasons=("The engine cannot validate a setup without fresh price and completed candles.",),
                now=stamp,
                regime=MarketRegime.NORMAL,
                alignment=TimeframeAlignment.NO_TRADE,
                confluence_score=0,
                risk_reward_ratio=0.0,
            )

        daily, h4, h1 = mtf.daily, mtf.four_hour, mtf.one_hour
        trend, structure, momentum = daily.direction, h4.direction, h1.direction

        # 2. MULTI-TIMEFRAME ALIGNMENT CLASSIFICATION
        alignment = _classify_alignment(trend, structure, momentum)
        directional = trend if trend in {"BULLISH", "BEARISH"} and trend == structure else None

        # 3. VOLATILITY & MARKET REGIME DETECTION
        volatility_ratio = atr / price
        valid_volatility = volatility_ratio <= 0.055
        volatility = "NORMAL" if valid_volatility else "HIGH"

        trigger_level = h1.trigger_level
        invalidation, targets, actual_rr = _risk_levels(
            "LONG" if directional == "BULLISH" else "SHORT" if directional == "BEARISH" else "NEUTRAL",
            price,
            atr,
            h1.invalidation_level,
            h1.objective_level,
        )

        regime = _classify_regime(
            trend=trend,
            structure=structure,
            momentum=momentum,
            volatility_ratio=volatility_ratio,
            price=price,
            trigger_level=trigger_level,
            invalidation=invalidation,
            atr=atr,
        )

        # 4. UNALIGNED / CONFLICTING TIMEFRAMES -> STRICT NO_TRADE
        if directional is None:
            self.rejected_count += 1
            blocker = (
                "Daily trend and 4H structure are in active conflict."
                if alignment == TimeframeAlignment.CONFLICT
                else "Daily trend and 4H structure are not directionally aligned."
            )
            return self._snapshot(
                state="NO_TRADE",
                setup="No aligned setup",
                direction=None,
                confidence=_no_trade_confidence(trend, structure, momentum),
                trend=trend,
                structure=structure,
                momentum=momentum,
                volatility=volatility,
                breakout="WAITING",
                confirmation="NONE",
                risk_reward="NOT EVALUATED",
                blocker=blocker,
                trigger_level=trigger_level,
                reasons=(
                    f"Higher-timeframe hierarchy is {alignment.replace('_', ' ')}.",
                    f"Daily trend is {trend}; 4H structure is {structure}; 1H momentum is {momentum}.",
                    "The system enforces strict multi-timeframe alignment before committing capital.",
                ),
                now=stamp,
                regime=regime,
                alignment=alignment,
                confluence_score=15 if alignment == TimeframeAlignment.MIXED else 0,
                risk_reward_ratio=0.0,
            )

        direction = "LONG" if directional == "BULLISH" else "SHORT"
        rr_ok = actual_rr >= 1.8
        momentum_aligned = momentum == daily.direction
        completed_breakout = bool(h1.trigger)
        price_broke = price >= trigger_level if (direction == "LONG" and trigger_level) else price <= trigger_level if (direction == "SHORT" and trigger_level) else False

        # 5. ORTHOGONAL CONFLUENCE SCORING
        confluence = _calculate_confluence(
            alignment=alignment,
            regime=regime,
            actual_rr=actual_rr,
            rr_ok=rr_ok,
            momentum_aligned=momentum_aligned,
            completed_breakout=completed_breakout,
            valid_volatility=valid_volatility,
            d_conf=daily.confidence,
            h4_conf=h4.confidence,
            h1_conf=h1.confidence,
            price=price,
            invalidation=invalidation,
            atr=atr,
        )

        reasons = [
            f"Daily trend ({trend}) and 4H structure ({structure}) are aligned {direction.lower()}.",
            f"Multi-timeframe hierarchy confirms {alignment.replace('_', ' ')} (regime: {regime.replace('_', ' ')}).",
            f"1H momentum is {momentum.lower()} with trigger level at {trigger_level:.2f}." if trigger_level else f"1H momentum is {momentum.lower()}.",
            "Volatility is within the configured risk envelope." if valid_volatility else "Volatility is elevated; entries are paused.",
            f"Market-structure objective provides {actual_rr:.1f}R to the first target.",
        ]
        if completed_breakout:
            reasons.append("The latest completed 1H candle confirmed the breakout condition.")

        # 6. MARKET SESSION CHECK
        if not market_open:
            self.rejected_count += 1
            blocker = "MCX Natural Gas market is closed. Entries paused until market opens (09:00 IST)."
            return self._snapshot(
                state="WATCH_LONG" if direction == "LONG" else "WATCH_SHORT",
                setup="Developing (Market Closed)",
                direction=direction,
                confidence=confluence,
                trend=trend,
                structure=structure,
                momentum=momentum,
                volatility=volatility,
                breakout="WAITING",
                confirmation="MARKET CLOSED",
                risk_reward="VALID" if rr_ok else "INSUFFICIENT",
                blocker=blocker,
                trigger_level=trigger_level,
                invalidation=invalidation,
                targets=targets,
                reasons=tuple(reasons + ["MCX regular session is closed; triggers cannot fire."]),
                now=stamp,
                regime=regime,
                alignment=alignment,
                confluence_score=confluence,
                risk_reward_ratio=actual_rr,
            )

        # 7. QUALIFYING FILTERS GATE (Volatility, Momentum, Risk/Reward)
        if not valid_volatility or not momentum_aligned or not rr_ok:
            self.rejected_count += 1
            blocker = (
                "Volatility is elevated."
                if not valid_volatility
                else "1H momentum has not confirmed the higher-timeframe setup."
                if not momentum_aligned
                else "Risk/reward is below 1.8R."
            )
            return self._snapshot(
                state="WATCH_LONG" if direction == "LONG" else "WATCH_SHORT",
                setup="Developing",
                direction=direction,
                confidence=confluence,
                trend=trend,
                structure=structure,
                momentum=momentum,
                volatility=volatility,
                breakout="WAITING",
                confirmation="PARTIAL",
                risk_reward="VALID" if rr_ok else "INSUFFICIENT",
                blocker=blocker,
                trigger_level=trigger_level,
                invalidation=invalidation,
                targets=targets,
                reasons=tuple(reasons),
                now=stamp,
                regime=regime,
                alignment=alignment,
                confluence_score=confluence,
                risk_reward_ratio=actual_rr,
            )

        # 8. COOLDOWN GATE (Anti-churn protection)
        if self._cooldown_remaining > 0:
            self._cooldown_remaining -= 1
            return self._snapshot(
                state="COOLDOWN",
                setup="Triggered setup monitored",
                direction=direction,
                confidence=confluence,
                trend=trend,
                structure=structure,
                momentum=momentum,
                volatility=volatility,
                breakout="CONFIRMED",
                confirmation="COMPLETE",
                risk_reward="VALID",
                blocker="Duplicate trigger cooldown is active.",
                trigger_level=trigger_level,
                invalidation=invalidation,
                targets=targets,
                reasons=tuple(reasons),
                now=stamp,
                regime=regime,
                alignment=alignment,
                confluence_score=confluence,
                risk_reward_ratio=actual_rr,
            )

        # 9. TRIGGER GATE (Actionable entry)
        if completed_breakout and price_broke:
            state: BrainState = "LONG_TRIGGER" if direction == "LONG" else "SHORT_TRIGGER"
            self._cooldown_remaining = self.cooldown_cycles
            self._add_event(now, f"{direction} trigger", confluence, f"Completed 1H breakout confirmed at {price:.2f} ({actual_rr:.1f}R).")
            self._paper.append(
                PaperSignal(
                    direction=direction,
                    entry=price,
                    stop=invalidation,
                    target1=targets[0],
                    target2=targets[1],
                    confidence=confluence,
                    opened_at=stamp,
                    trailing_stop=invalidation,
                    r_multiple=actual_rr,
                )
            )
            return self._snapshot(
                state=state,
                setup="Actionable",
                direction=direction,
                confidence=confluence,
                trend=trend,
                structure=structure,
                momentum=momentum,
                volatility=volatility,
                breakout="CONFIRMED",
                confirmation="COMPLETE",
                risk_reward="VALID",
                blocker="No blocker; paper-validation tracking started.",
                trigger_level=trigger_level,
                invalidation=invalidation,
                targets=targets,
                reasons=tuple(reasons),
                now=stamp,
                regime=regime,
                alignment=alignment,
                confluence_score=confluence,
                risk_reward_ratio=actual_rr,
            )

        # 10. WATCH STATE (Setup valid, awaiting completed 1H breakout)
        state = "WATCH_LONG" if direction == "LONG" else "WATCH_SHORT"
        trigger_desc = f"{trigger_level:.2f}" if trigger_level is not None else "trigger level"
        blocker = f"Waiting for a completed 1H close {'above' if direction == 'LONG' else 'below'} {trigger_desc}."
        if self.current_state != state:
            self._add_event(now, f"{direction} setup detected", confluence, blocker)

        return self._snapshot(
            state=state,
            setup="Developing",
            direction=direction,
            confidence=confluence,
            trend=trend,
            structure=structure,
            momentum=momentum,
            volatility=volatility,
            breakout="WAITING",
            confirmation="PARTIAL",
            risk_reward="VALID",
            blocker=blocker,
            trigger_level=trigger_level,
            invalidation=invalidation,
            targets=targets,
            reasons=tuple(reasons),
            now=stamp,
            regime=regime,
            alignment=alignment,
            confluence_score=confluence,
            risk_reward_ratio=actual_rr,
        )

    def _snapshot(
        self,
        *,
        state: BrainState,
        setup: str,
        direction: str | None,
        confidence: int,
        trend: str,
        structure: str,
        momentum: str,
        volatility: str,
        breakout: str,
        confirmation: str,
        risk_reward: str,
        blocker: str,
        reasons: tuple[str, ...],
        now: str,
        trigger_level: float | None = None,
        invalidation: float | None = None,
        targets: tuple[float, float] | tuple[()] = (),
        regime: str = MarketRegime.NORMAL,
        alignment: str = TimeframeAlignment.MIXED,
        confluence_score: int = 0,
        risk_reward_ratio: float = 0.0,
        setup_type: str = "BREAKOUT_EXPANSION",
    ) -> BrainSnapshot:
        if state != self.current_state and state == "NO_TRADE":
            self._add_event(datetime.fromisoformat(now), "Setup rejected", confidence, blocker)
        self.current_state = state
        return BrainSnapshot(
            state=state,
            setup=setup,
            direction=direction,
            confidence=confidence,
            trend=trend,
            structure=structure,
            momentum=momentum,
            volatility=volatility,
            breakout=breakout,
            confirmation=confirmation,
            risk_reward=risk_reward,
            blocker=blocker,
            next_trigger=(f"Price {'>' if direction == 'LONG' else '<'} {trigger_level:.2f}" if trigger_level else None),
            trigger_level=trigger_level,
            invalidation=invalidation,
            targets=targets,
            reasons=reasons,
            unavailable_context=(
                "Macro / USD: DATA UNAVAILABLE",
                "Crude relationship: DATA UNAVAILABLE",
                "News-event feed: DATA UNAVAILABLE",
            ),
            evaluation_count=self.evaluation_count,
            rejected_count=self.rejected_count,
            last_evaluated_at=now,
            events=tuple(self._events[-25:]),
            paper_signals=tuple(self._paper[-20:]),
            regime=regime,
            alignment=alignment,
            confluence_score=confluence_score,
            risk_reward_ratio=risk_reward_ratio,
            setup_type=setup_type,
        )

    def _add_event(self, now: datetime, event: str, confidence: int, detail: str) -> None:
        self._events.append(BrainEvent(now.isoformat(), event, confidence, detail))

    def _update_paper(self, price: float, now: datetime) -> None:
        for signal in self._paper:
            if signal.outcome != "OPEN":
                continue
            move = price - signal.entry if signal.direction == "LONG" else signal.entry - price
            signal.mfe = max(signal.mfe, move)
            signal.mae = min(signal.mae, move)

            # Invalidation Check
            current_stop = signal.trailing_stop if signal.trailing_stop is not None else signal.stop
            if (signal.direction == "LONG" and price <= current_stop) or (signal.direction == "SHORT" and price >= current_stop):
                signal.outcome = "SL_HIT"
                signal.closed_at = now.isoformat()
            # TP2 Check
            elif (signal.direction == "LONG" and price >= signal.target2) or (signal.direction == "SHORT" and price <= signal.target2):
                signal.outcome = "TP2_HIT"
                signal.closed_at = now.isoformat()
            # TP1 Check -> Lock in breakeven trailing stop
            elif (signal.direction == "LONG" and price >= signal.target1) or (signal.direction == "SHORT" and price <= signal.target1):
                signal.outcome = "TP1_HIT"
                signal.closed_at = now.isoformat()
                signal.trailing_stop = signal.entry  # Breakeven ratchet protects profits


def _classify_alignment(trend: str, structure: str, momentum: str) -> str:
    """Classifies multi-timeframe alignment across 1D, 4H, and 1H."""
    if trend in {"BULLISH", "BEARISH"} and structure == trend:
        if momentum == trend:
            return TimeframeAlignment.STRONG_ALIGNMENT
        return TimeframeAlignment.PARTIAL_ALIGNMENT
    if trend in {"BULLISH", "BEARISH"} and structure in {"BULLISH", "BEARISH"} and trend != structure:
        return TimeframeAlignment.CONFLICT
    if trend in {"BULLISH", "BEARISH"} or structure in {"BULLISH", "BEARISH"}:
        return TimeframeAlignment.MIXED
    return TimeframeAlignment.NO_TRADE


def _classify_regime(
    trend: str,
    structure: str,
    momentum: str,
    volatility_ratio: float,
    price: float,
    trigger_level: float | None,
    invalidation: float | None,
    atr: float,
) -> str:
    """Detects market regime based on volatility, timeframe posture, and price extension."""
    if volatility_ratio > 0.055:
        return MarketRegime.HIGH_VOLATILITY
    if volatility_ratio < 0.020:
        return MarketRegime.COMPRESSION_SQUEEZE

    # Check for overextension
    if invalidation is not None and abs(price - invalidation) > 2.5 * atr:
        return MarketRegime.EXHAUSTION_REVERSAL

    if trend in {"BULLISH", "BEARISH"} and structure == trend:
        if momentum == trend:
            return MarketRegime.TRENDING_EXPANSION
        return MarketRegime.TRENDING_PULLBACK

    return MarketRegime.RANGE_CONSOLIDATION


def _calculate_confluence(
    alignment: str,
    regime: str,
    actual_rr: float,
    rr_ok: bool,
    momentum_aligned: bool,
    completed_breakout: bool,
    valid_volatility: bool,
    d_conf: float,
    h4_conf: float,
    h1_conf: float,
    price: float,
    invalidation: float | None,
    atr: float,
) -> int:
    """Computes a multi-factor confluence score (0-100%) across 5 orthogonal pillars."""
    score = 0.0

    # Pillar 1: Timeframe Alignment & Weight (Max 38 pts)
    score += 18.0 * min(1.0, max(0.0, d_conf))
    score += 12.0 * min(1.0, max(0.0, h4_conf))
    score += 8.0 * min(1.0, max(0.0, h1_conf))
    if alignment == TimeframeAlignment.STRONG_ALIGNMENT:
        score += 8.0
    elif alignment == TimeframeAlignment.PARTIAL_ALIGNMENT:
        score += 4.0

    # Pillar 2: Regime Fit (Max 16 pts)
    if regime == MarketRegime.TRENDING_EXPANSION:
        score += 16.0
    elif regime == MarketRegime.COMPRESSION_SQUEEZE:
        score += 14.0
    elif regime == MarketRegime.TRENDING_PULLBACK:
        score += 12.0
    elif regime == MarketRegime.RANGE_CONSOLIDATION:
        score += 6.0
    # HIGH_VOLATILITY and EXHAUSTION receive 0 pts

    # Pillar 3: Structural Risk/Reward (Max 18 pts)
    if rr_ok:
        if actual_rr >= 2.4:
            score += 18.0
        elif actual_rr >= 2.0:
            score += 15.0
        else:
            score += 12.0

    # Pillar 4: Trigger & Momentum (Max 16 pts)
    if momentum_aligned:
        score += 8.0
    if completed_breakout:
        score += 8.0
    else:
        score += 3.0

    # Pillar 5: Distance & Volatility Envelope (Max 12 pts)
    if valid_volatility:
        score += 6.0
        if invalidation is not None:
            dist = abs(price - invalidation)
            if dist <= 1.8 * atr:
                score += 6.0
            elif dist <= 2.4 * atr:
                score += 3.0

    return min(100, round(score))


def _no_trade_confidence(trend: str, structure: str, momentum: str) -> int:
    return 42 if trend == momentum and trend in {"BULLISH", "BEARISH"} else 25


def _risk_levels(
    direction: str,
    price: float,
    atr: float,
    structural_invalidation: float | None,
    structural_objective: float | None,
) -> tuple[float, tuple[float, float], float]:
    min_risk = max(atr * 0.5, 0.01)
    if direction == "LONG":
        stop = structural_invalidation if structural_invalidation is not None else price - atr
        stop = min(stop, price - min_risk)
        risk = price - stop
        objective = structural_objective if structural_objective is not None else price + 2.0 * risk
        target1, target2 = objective, max(objective, price + 2.6 * risk)
    elif direction == "SHORT":
        stop = structural_invalidation if structural_invalidation is not None else price + atr
        stop = max(stop, price + min_risk)
        risk = stop - price
        objective = structural_objective if structural_objective is not None else price - 2.0 * risk
        target1, target2 = objective, min(objective, price - 2.6 * risk)
    else:
        return price - atr, (price + 2.0 * atr, price + 2.6 * atr), 0.0

    if risk <= 0:
        return stop, (target1, target2), 0.0
    return stop, (target1, target2), abs(target1 - price) / risk
