# NATGAS Trader + Risk Engine

The final research decision layer is now implemented.

## Pipeline

1. Deterministic market/technical evidence
2. Exa source discovery
3. Llama Bull/Bear research
4. Bull/Bear debate
5. Trader + Risk geometry
6. Structured `NatgasDecision`

## Output contract

Every directional research result contains:

- instrument
- direction
- confidence
- entry zone
- invalidation
- two targets
- rationale
- catalysts
- risks

## Hard NO_TRADE gates

The engine refuses a directional result when:

- current price is invalid
- ATR/risk distance is unavailable
- required evidence contains data gaps
- bull/bear evidence is balanced or explicitly unresolved
- final evidence confidence is below threshold
- entry/invalidation/target geometry fails validation

The engine is research-only. It does not place broker orders.

## Risk geometry

For the current implementation:

- entry = supplied validated current price
- invalidation = 1.0 ATR from entry
- target 1 = 1.5 ATR
- target 2 = 2.5 ATR
- displayed entry zone = +/- 0.20 ATR

These are deterministic research parameters, not claims of optimality or profitability. They must be validated separately against historical data before being treated as a strategy.
