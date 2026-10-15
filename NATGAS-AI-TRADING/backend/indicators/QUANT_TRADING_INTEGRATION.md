# Quant-trading integration

The NATGAS desk now incorporates research ideas from [je-suis-tm/quant-trading](https://github.com/je-suis-tm/quant-trading).

The upstream project is an Apache-2.0 Python research repository containing standalone backtests for MACD, Bollinger Bands, Awesome Oscillator, Dual Thrust, Parabolic SAR, Heikin-Ashi, RSI pattern recognition and candlestick patterns.

## How we use it

We do **not** copy the upstream scripts into the live pipeline or inherit their frictionless-trading assumptions. Instead, the NATGAS project implements deterministic indicator features in `backend/indicators/technical.py` and feeds them into `backend/natgas/quant_ensemble.py`.

Current features:

- MACD and signal/histogram
- Bollinger Bands and bandwidth
- Awesome Oscillator
- Heikin-Ashi state
- Parabolic SAR
- Dual-Thrust-style reference levels
- Shooting-star geometry
- Existing SMA/EMA/RSI features

The resulting technical evidence is advisory and auditable. Conflicting indicator evidence remains visible and can contribute to a `NO_TRADE` outcome.

The upstream repository is used as research inspiration/reference; its Apache-2.0 license and attribution remain applicable to any code directly copied from it. The NATGAS implementation in this integration is original.
