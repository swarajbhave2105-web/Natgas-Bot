# Live Final Decision Wiring

The NIFTY desk now wires the live TradingView layer into the final Trader + Risk engine.

**Flow**

TradingView `NSE:NIFTY`
→ live quote
→ TradingView OHLC bars
→ deterministic technical indicators
→ ATR(14)
→ SMA20/SMA50 regime
→ analyst evidence + Bull/Bear debate
→ Trader + Risk engine
→ structured `NiftyDecision`

The live bar endpoint defaults to daily bars and requests a bounded history window.

The engine fails closed when the quote is disconnected/stale, bars are insufficient, ATR is unavailable, evidence has gaps, or the final evidence gate does not support a directional research decision.

No broker execution or order placement is connected.
