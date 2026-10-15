# NATGAS AI Trading — Pipeline Status

## Milestone: Live TradingView market layer

The research pipeline now has a guarded live-market boundary:

TradingView MCX:NATURALGAS1! -> Node live quote bridge -> Python live snapshot -> analyst pipeline

The live layer captures the current quote and rejects analysis when the feed is disconnected, stale, missing a price, or not reported as realtime.

Required analyst evidence roles remain:
- Technical
- Fundamental
- Weather
- Macro
- News
- Risk

The pipeline does not place orders and does not manufacture missing observations.

## Next milestone

Feed the timestamped live snapshot into the technical indicator engine, then add Bull/Bear debate inputs using the same market snapshot.
