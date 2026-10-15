# NATGAS TradingView Live Feed

This service bridges the TradingView MCX Natural Gas continuous contract into the NATGAS AI Trading Desk.

Default symbol:

`MCX:NATURALGAS1!`

TradingView identifies this as the MCX Natural Gas continuous contract.

## Run

```bash
cd live_feed
npm install
npm start
```

Optional environment variables:

- `TRADINGVIEW_SYMBOL`
- `TRADINGVIEW_FEED_PORT` (default 8787)
- `TRADINGVIEW_MAX_STALE_MS` (default 15000)

Endpoints:

- `GET /health`
- `GET /quote`

The bridge is read-only. It never places orders.

The Python backend should consume `/quote` and enforce the stale-data guard before producing a fresh decision.
