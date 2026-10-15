# Live Market Data Rules

Live market data is a critical system.

Never label delayed, cached, stale, simulated, public-demo or fallback data as LIVE.

Every live-data pipeline should account for:
* source
* instrument
* timestamp
* freshness
* connection state
* heartbeat/health
* reconnection state
* last successful event
* error state

When investigating latency, measure the complete path:
SOURCE
→ PROVIDER
→ INGESTION
→ BACKEND
→ STREAM/API
→ CLIENT
→ BROWSER DISPLAY

Do not claim zero-latency or real-time behavior without measurement.

Do not improve apparent latency by removing validation, freshness checks or correctness safeguards.

If a live feed becomes stale or disconnected, the system should expose that state rather than silently presenting the last price as current.

Do not silently substitute a different market-data source when the requested source is unavailable.

Any fallback mechanism must be explicitly identified as FALLBACK/DELAYED/etc.
