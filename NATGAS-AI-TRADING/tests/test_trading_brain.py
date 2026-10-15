from backend.natgas.analysts import AnalystEvidence
from backend.natgas.multi_timeframe import MultiTimeframeAnalysis, TimeframeAnalysis
from backend.natgas.trading_brain import TradingBrain


def mtf(daily="BULLISH", structure="BULLISH", momentum="BULLISH", trigger=None, level=101.0):
    evidence = AnalystEvidence("technical", daily, 0.9, [], [], [])
    return MultiTimeframeAnalysis(
        TimeframeAnalysis("1D", 120, daily, 0.9, (), (), None),
        TimeframeAnalysis("4H", 120, structure, 0.8, (), (), None),
        TimeframeAnalysis("1H", 120, momentum, 0.75, (), (), trigger, level),
        evidence,
    )


def test_long_watch_then_completed_breakout_triggers_and_enters_cooldown():
    brain = TradingBrain(cooldown_cycles=2)
    watch = brain.evaluate(price=100, atr=2, mtf=mtf(), data_fresh=True)
    assert watch.state == "WATCH_LONG"
    assert watch.trigger_level == 101
    trigger = brain.evaluate(price=102, atr=2, mtf=mtf(trigger="LONG_1H_CLOSE_ABOVE_PRIOR_5_BAR_HIGH"), data_fresh=True)
    assert trigger.state == "LONG_TRIGGER"
    assert trigger.invalidation < 102 < trigger.targets[0]
    duplicate = brain.evaluate(price=102.1, atr=2, mtf=mtf(trigger="LONG_1H_CLOSE_ABOVE_PRIOR_5_BAR_HIGH"), data_fresh=True)
    assert duplicate.state == "COOLDOWN"
    assert len(trigger.paper_signals) == 1


def test_short_trigger_and_paper_outcome_are_tracked():
    brain = TradingBrain()
    signal = brain.evaluate(price=98, atr=2, mtf=mtf("BEARISH", "BEARISH", "BEARISH", "SHORT_1H_CLOSE_BELOW_PRIOR_5_BAR_LOW", 99), data_fresh=True)
    assert signal.state == "SHORT_TRIGGER"
    target1 = signal.targets[0]
    result = brain.evaluate(price=target1, atr=2, mtf=mtf("BEARISH", "BEARISH", "BEARISH", "SHORT_1H_CLOSE_BELOW_PRIOR_5_BAR_LOW", 99), data_fresh=True)
    assert result.paper_signals[0].outcome == "TP1_HIT"


def test_market_closed_prevents_trigger_and_keeps_watch_mode():
    brain = TradingBrain()
    result = brain.evaluate(
        price=102,
        atr=2,
        mtf=mtf(trigger="LONG_1H_CLOSE_ABOVE_PRIOR_5_BAR_HIGH"),
        data_fresh=True,
        market_open=False,
    )
    assert result.state == "WATCH_LONG"
    assert result.confirmation == "MARKET CLOSED"
    assert "market is closed" in result.blocker.lower()
    assert len(result.paper_signals) == 0


def test_independent_structural_risk_reward_enforces_1_8r_minimum():
    evidence = AnalystEvidence("technical", "BULLISH", 0.9, [], [], [])
    # Provide tight structural objective that yields < 1.8R
    poor_rr_mtf = MultiTimeframeAnalysis(
        TimeframeAnalysis("1D", 120, "BULLISH", 0.9, (), (), None),
        TimeframeAnalysis("4H", 120, "BULLISH", 0.8, (), (), None),
        TimeframeAnalysis(
            "1H", 120, "BULLISH", 0.75, (), (),
            trigger="LONG_1H_CLOSE_ABOVE_PRIOR_5_BAR_HIGH",
            trigger_level=101.0,
            invalidation_level=98.0,  # 3 pts risk at entry 101 -> risk=3
            objective_level=104.0,   # 3 pts reward -> R:R = 1.0 < 1.8R
        ),
        evidence,
    )
    brain = TradingBrain()
    blocked = brain.evaluate(price=101.5, atr=2.0, mtf=poor_rr_mtf, data_fresh=True)
    assert blocked.state == "WATCH_LONG"
    assert blocked.risk_reward == "INSUFFICIENT"
    assert "risk/reward is below 1.8r" in blocked.blocker.lower()


def test_conflict_high_volatility_and_missing_data_do_not_trigger():
    brain = TradingBrain()
    conflict = brain.evaluate(price=100, atr=2, mtf=mtf(structure="BEARISH"), data_fresh=True)
    assert conflict.state == "NO_TRADE"
    volatile = brain.evaluate(price=102, atr=8, mtf=mtf(trigger="LONG_1H_CLOSE_ABOVE_PRIOR_5_BAR_HIGH"), data_fresh=True)
    assert volatile.state == "WATCH_LONG"
    assert volatile.volatility == "HIGH"
    missing = brain.evaluate(price=0, atr=None, mtf=None, data_fresh=False)
    assert missing.state == "NO_TRADE"
    assert "unavailable" in missing.blocker.lower()


def test_failed_breakout_invalidates_paper_signal_then_allows_a_new_setup():
    brain = TradingBrain(cooldown_cycles=0)
    triggered = brain.evaluate(price=102, atr=2, mtf=mtf(trigger="LONG_1H_CLOSE_ABOVE_PRIOR_5_BAR_HIGH"), data_fresh=True)
    assert triggered.state == "LONG_TRIGGER"
    stopped = brain.evaluate(price=99.5, atr=2, mtf=mtf(), data_fresh=True)
    assert stopped.paper_signals[0].outcome == "SL_HIT"
    recovered = brain.evaluate(price=98, atr=2, mtf=mtf("BEARISH", "BEARISH", "BEARISH"), data_fresh=True)
    assert recovered.state == "WATCH_SHORT"

    
def test_forming_intraday_candle_is_excluded_until_full_interval_has_elapsed():
    import time
    import pandas as pd
    from backend.natgas.live_final import _closed_intraday_bars
    now = time.time()
    frame = pd.DataFrame([
        {"time": now - 3700, "open": 1, "high": 2, "low": 0, "close": 1.5},
        {"time": now - 3599, "open": 1, "high": 3, "low": 0, "close": 2},
    ])
    closed = _closed_intraday_bars(frame, hours=1)
    assert len(closed) == 1


def test_multi_timeframe_alignment_classifications():
    from backend.natgas.trading_brain import TimeframeAlignment
    brain = TradingBrain()

    strong = brain.evaluate(price=100, atr=2, mtf=mtf("BULLISH", "BULLISH", "BULLISH"), data_fresh=True)
    assert strong.alignment == TimeframeAlignment.STRONG_ALIGNMENT

    partial = brain.evaluate(price=100, atr=2, mtf=mtf("BULLISH", "BULLISH", "BEARISH"), data_fresh=True)
    assert partial.alignment == TimeframeAlignment.PARTIAL_ALIGNMENT

    conflict = brain.evaluate(price=100, atr=2, mtf=mtf("BULLISH", "BEARISH", "BULLISH"), data_fresh=True)
    assert conflict.alignment == TimeframeAlignment.CONFLICT
    assert conflict.state == "NO_TRADE"


def test_market_regime_detection_and_confluence_payload():
    from backend.natgas.trading_brain import MarketRegime
    brain = TradingBrain()

    res = brain.evaluate(price=100, atr=2, mtf=mtf("BULLISH", "BULLISH", "BULLISH"), data_fresh=True)
    assert res.regime == MarketRegime.TRENDING_EXPANSION
    assert res.confluence_score > 60
    assert "regime" in res.payload()
    assert "alignment" in res.payload()
    assert "confluence_score" in res.payload()
    assert "risk_reward_ratio" in res.payload()

    squeeze = brain.evaluate(price=100, atr=1.5, mtf=mtf("BULLISH", "BULLISH", "BULLISH"), data_fresh=True)
    assert squeeze.regime == MarketRegime.COMPRESSION_SQUEEZE


def test_trailing_breakeven_ratchet_on_tp1():
    brain = TradingBrain()
    signal = brain.evaluate(
        price=98, atr=2,
        mtf=mtf("BEARISH", "BEARISH", "BEARISH", "SHORT_1H_CLOSE_BELOW_PRIOR_5_BAR_LOW", 99),
        data_fresh=True
    )
    assert signal.state == "SHORT_TRIGGER"
    target1 = signal.targets[0]

    # Reach TP1
    result = brain.evaluate(
        price=target1, atr=2,
        mtf=mtf("BEARISH", "BEARISH", "BEARISH", "SHORT_1H_CLOSE_BELOW_PRIOR_5_BAR_LOW", 99),
        data_fresh=True
    )
    paper = result.paper_signals[0]
    assert paper.outcome == "TP1_HIT"
    assert paper.trailing_stop == 98.0  # Trailing stop ratcheted to breakeven entry


