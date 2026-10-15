const http = require("http");
const TradingView = require("@mathieuc/tradingview");

const PORT = Number(process.env.TRADINGVIEW_FEED_PORT || 8787);
const SYMBOL = process.env.TRADINGVIEW_SYMBOL || "MCX:NATURALGAS1!";
const MAX_STALE_MS = Number(process.env.TRADINGVIEW_MAX_STALE_MS || 15000);
const TRADINGVIEW_SESSION_ID = process.env.TRADINGVIEW_SESSION_ID || "";
const TRADINGVIEW_SESSION_SIGNATURE = process.env.TRADINGVIEW_SESSION_SIGNATURE || "";
const TRADINGVIEW_LOCATION = process.env.TRADINGVIEW_LOCATION || "https://in.tradingview.com";

let latestQuote = null;
let connected = false;
let lastError = null;
let client;
let quoteSession;
let market;
let chart;

function applyQuote(data, realtime = true) {
  if (!data) return;
  latestQuote = {
    ...data,
    received_at_ms: Date.now(),
    source: "tradingview",
    symbol: SYMBOL,
    realtime,
  };
  connected = true;
  lastError = null;
}

function startQuoteSession() {
  quoteSession = new client.Session.Quote({
    customFields: [
      "lp", "bid", "ask", "volume", "open_price", "high_price",
      "low_price", "prev_close_price", "ch", "chp", "exchange",
      "currency_code", "timezone", "current_session", "is_tradable",
      "update_mode", "type", "description",
    ],
  });

  market = new quoteSession.Market(SYMBOL, "regular");

  market.onLoaded(() => {
    connected = true;
    console.log("TradingView quote loaded for " + SYMBOL);
  });

  market.onData((data) => {
    applyQuote(data, true);
  });

  market.onError((error) => {
    connected = false;
    lastError = error && error.message ? error.message : String(error);
    console.error("TradingView quote error:", lastError);
  });
}

function startChartFallback() {
  chart = new client.Session.Chart();
  chart.setMarket(SYMBOL, {
    timeframe: "1",
    range: 2,
    to: Math.floor(Date.now() / 1000),
  });

  chart.onSymbolLoaded(() => {
    console.log("TradingView chart loaded for " + SYMBOL);
  });

  chart.onUpdate(() => {
    const periods = chart.periods || [];
    const p = periods[periods.length - 1];
    if (!p) return;

    const close = Number(p.ClosePrice);
    const open = Number(p.OpenPrice);
    const high = Number(p.MaxPrice);
    const low = Number(p.MinPrice);
    const volume = Number(p.Volume || 0);

    if (![close, open, high, low].every(Number.isFinite)) return;

    applyQuote({
      lp: close,
      bid: null,
      ask: null,
      volume,
      open_price: open,
      high_price: high,
      low_price: low,
      prev_close_price: null,
      ch: null,
      chp: null,
      exchange: "MCX",
      currency_code: null,
      timezone: null,
      current_session: null,
      is_tradable: true,
      update_mode: "streaming",
      type: "futures",
      description: SYMBOL,
      chart_bar_time: p.$time,
    }, true);
  });

  chart.onError((error) => {
    lastError = error && error.message ? error.message : String(error);
    console.error("TradingView chart error:", lastError);
  });
}

function publicQuote() {
  const stale =
    !latestQuote ||
    Date.now() - latestQuote.received_at_ms > MAX_STALE_MS;

  return {
    source: "tradingview",
    symbol: SYMBOL,
    connected,
    realtime: latestQuote ? latestQuote.realtime !== false : null,
    last_update_ms: latestQuote ? latestQuote.received_at_ms : null,
    stale,
    quote: latestQuote,
    error: lastError,
  };
}

function getBars(res, url) {
  const query = new URL(url, "http://127.0.0.1").searchParams;
  const timeframe =
    query.get("timeframe") ||
    process.env.TRADINGVIEW_TIMEFRAME ||
    "D";
  const range = Math.min(
    500,
    Math.max(
      20,
      Number(
        query.get("range") ||
          process.env.TRADINGVIEW_BAR_RANGE ||
          120
      )
    )
  );

  try {
    const localChart = new client.Session.Chart();
    localChart.setMarket(SYMBOL, {
      timeframe,
      range,
      to: Math.floor(Date.now() / 1000),
    });

    localChart.onUpdate(() => {
      const bars = (localChart.periods || [])
        .slice(-range)
        .map((p) => ({
          time: p.$time,
          open: Number(p.OpenPrice),
          high: Number(p.MaxPrice),
          low: Number(p.MinPrice),
          close: Number(p.ClosePrice),
          volume: Number(p.Volume || 0),
        }))
        .filter(
          (p) =>
            Number.isFinite(p.open) &&
            Number.isFinite(p.high) &&
            Number.isFinite(p.low) &&
            Number.isFinite(p.close)
        );

      localChart.delete();

      return sendJson(res, 200, {
        source: "tradingview",
        symbol: SYMBOL,
        timeframe,
        realtime: true,
        bars,
      });
    });

    localChart.onError((error) => {
      localChart.delete();
      return sendJson(res, 502, {
        error: error && error.message ? error.message : String(error),
      });
    });
  } catch (error) {
    return sendJson(res, 502, {
      error: error && error.message ? error.message : String(error),
    });
  }
}

function sendJson(res, status, payload) {
  res.writeHead(status, {
    "Content-Type": "application/json; charset=utf-8",
    "Cache-Control": "no-store",
  });
  res.end(JSON.stringify(payload));
}

const server = http.createServer((req, res) => {
  const pathname = new URL(req.url, "http://127.0.0.1").pathname;

  if (pathname === "/health" || pathname === "/quote") {
    return sendJson(res, 200, publicQuote());
  }

  if (pathname === "/bars") {
    return getBars(res, req.url);
  }

  return sendJson(res, 404, { error: "not_found" });
});

const clientOptions = {
  location: TRADINGVIEW_LOCATION,
};

// MCX market data is entitlement-controlled on TradingView. When supplied,
// these existing browser-session cookies allow the bridge to use the user's
// entitled TradingView data feed without exposing credentials in logs.
if (TRADINGVIEW_SESSION_ID) {
  clientOptions.token = TRADINGVIEW_SESSION_ID;
  if (TRADINGVIEW_SESSION_SIGNATURE) {
    clientOptions.signature = TRADINGVIEW_SESSION_SIGNATURE;
  }
}

client = new TradingView.Client(clientOptions);
console.log(
  "TradingView client auth: " +
    (TRADINGVIEW_SESSION_ID ? "configured" : "anonymous") +
    ", location=" + TRADINGVIEW_LOCATION
);
if (!TRADINGVIEW_SESSION_ID) {
  lastError = "MCX_TRADINGVIEW_AUTH_REQUIRED";
  console.warn(
    "MCX data may require an entitled TradingView session. Set " +
      "TRADINGVIEW_SESSION_ID (and TRADINGVIEW_SESSION_SIGNATURE when required)."
  );
}

startQuoteSession();
startChartFallback();

server.listen(PORT, "127.0.0.1", () => {
  console.log(
    "NATGAS TradingView feed listening on :" +
      PORT +
      " for " +
      SYMBOL
  );
});

process.on("uncaughtException", (err) => {
  console.error("TradingView feed uncaught exception:", err && err.message ? err.message : String(err));
});

process.on("unhandledRejection", (reason) => {
  console.error("TradingView feed unhandled rejection:", reason && reason.message ? reason.message : String(reason));
});

process.on("SIGINT", async () => {

  try {
    if (market) market.close();
    if (quoteSession) quoteSession.delete();
    if (chart) chart.delete();
    if (client) await client.end();
  } finally {
    process.exit(0);
  }
});
