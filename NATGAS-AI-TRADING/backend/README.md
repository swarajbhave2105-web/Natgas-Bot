# NATGAS backend

The backend is intentionally split into four layers:

1. **Data** — MCX and reference-market providers.
2. **Features** — deterministic calculations and normalized snapshots.
3. **Decision** — auditable evidence aggregation with an explicit NO_TRADE state.
4. **AI orchestration** — to be connected to the TradingAgents framework after the data contracts are stable.

Live order execution is deliberately out of scope for V1.
