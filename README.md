# MT5 Python SDK Restfull – Documentation

## Contribute

You may contribute to this project by checking the **stability** of the app and sending PRs.
This project is designed as a core system; you can build wrappers around it using the REST and WebSocket APIs implemented (e.g., adding authentication, rate limiting, or paid subscriptions). Please reference this repository URL somewhere in your project if you use it.


## Support? (anything is appreciated)
ETH: ```0xee397779087244e0e2bc5cfb083f40ea0bb74f9e```

BTC: ```bc1quxmrn9wjh6k2r5wzj6wylnuedugnp325myznck```

SOL: ```DtotcL6XRgqF4h6UigeHGSQ7nMViAM9VEbCYnPx1183c```

BNB: ```0xee397779087244e0e2bc5cfb083f40ea0bb74f9e```

---

## Overview

This is a **FastAPI-based RESTful service** bridging to MetaTrader 5 (MT5). It loads configuration from JSON files (`config.dev.json` or `config.live.json`), initializes a **singleton MT5 connection**, and exposes endpoints for managing orders and positions. A WebSocket interface streams live prices and candle data to subscribed clients.

**Key Features:**

* Singleton MT5 connection for efficiency and thread safety.
* Supports demo/live accounts via CLI flag (`--live`).
* Logging to daily rotated files in `./logs` and console.
* Smart order types (e.g., `LIMIT` auto-resolves to `BUY_LIMIT` or `SELL_LIMIT` based on market prices).
* Validation for SL/TP minimum distances and pending order distances from market.
* Graceful shutdown on SIGINT/SIGTERM.
* WebSocket streaming of candles and live prices with configurable interval.

---

## Prerequisites

* Python 3.13.9 or compatible
* Install dependencies:

```bash
pip install -r requirements.txt
```

* MT5 terminal installed (path configured in JSON).
* Valid MT5 account credentials in `config.dev.json` / `config.live.json`.

---

## Configuration

**Common Config Options:**

```jsonc
{
  "accounts": {
    "live": { "login": 111111, "password": "PASSWORD", "server": "ServerName" },
    "demo": [
      { "login": 10008540762, "password": "_0WqDgUs", "server": "MetaQuotes-Demo" }
    ]
  },
  "mt5": {
    "path": "C:/Program Files/MetaTrader 5/terminal64.exe"
  },
  "server": {
    "host": "127.0.0.1",
    "port": 5100
  },
  "log_level": "INFO",
  "auth": {
    "enabled": false,
    "api_keys": []
  },
  "ws": {
    "interval_seconds": 1
  }
}
```

* `ws.interval_seconds` → Controls WebSocket and candle watcher refresh interval (default 1s).
* `accounts.demo` → List of demo accounts; `accounts.live` → Single live account.
* `mt5.path` → MT5 terminal executable path.
* `server.host/port` → HTTP server binding.
* `auth` → No built-in auth; wrappers can implement JWT/API keys.
* `log_level` → Logging verbosity: DEBUG, INFO, etc.

---

## Running the Service

```bash
# Demo mode
python src/main.py

# Live mode
python src/main.py --live
```

Server binds to `host:port` from config (default: `127.0.0.1:5100`). Logs at INFO level by default.

---

## Running Tests

```bash
pip install -r requirements.txt
pytest -v tests
```

---

## Base URL

```
http://<host>:<port>
```

* Example: `http://127.0.0.1:5100`
* API Version: `/api/v1`

---

## REST API

### Authentication

* No built-in authentication.
* Wrappers can add JWT/API keys or other middleware.

### Error Handling

* All responses include `success` (bool) and `message` (str).
* HTTP status 200 for all application-level errors; 4xx/5xx for server/validation issues.
* Optional `details` dictionary contains MT5 error codes.

Example:

```json
{
  "success": false,
  "message": "Invalid volume",
  "details": {"mt5_last_error": 10011}
}
```

---

## Endpoints

### Health Check

**GET /api/v1/health**

* Checks server and MT5 connection.

Response:

```json
{
  "status": "ok",
  "mt5_connected": true
}
```

---

### Place New Order

**POST /api/v1/orders/newOrder**

**Body: `NewOrderRequest`**

```json
{
  "symbol": "EURUSD",
  "volume": 0.05,
  "order_type": "BUY_LIMIT",
  "price": 1.08500,
  "sl": 1.08000,
  "tp": 1.09500,
  "deviation": 10,
  "comment": "strategy-v1",
  "magic": 12345,
  "client_id": "client-abc"
}
```

Response: `OrderResponse`

```json
{
  "success": true,
  "message": "Order placed",
  "ticket": 123456789,
  "symbol": "EURUSD",
  "order_type": "BUY_LIMIT",
  "price": 1.085,
  "volume": 0.05,
  "comment": "strategy-v1",
  "details": {"retcode": 10009}
}
```

---

### List Open Pending Orders

**GET /api/v1/orders/getOpenOrders**

* Optional query param: `symbol=EURUSD`

Response: `OrderListResponse`

```json
{
  "success": true,
  "message": "Open orders retrieved",
  "orders": [
    {
      "ticket": 123456789,
      "symbol": "EURUSD",
      "type": 0,
      "price": 1.085,
      "volume": 0.05,
      "sl": 1.08,
      "tp": 1.095,
      "time": 1733086412,
      "comment": "strategy-v1",
      "raw": {...}
    }
  ]
}
```

---

### List Open Positions

**GET /api/v1/orders/getOpenPositions**

* Optional query param: `symbol=GBPUSD`

Response: `PositionListResponse`

```json
{
  "success": true,
  "message": "Open positions retrieved",
  "positions": [
    {
      "ticket": 987654321,
      "symbol": "EURUSD",
      "type": 0,
      "volume": 0.05,
      "price_open": 1.08765,
      "sl": 1.08,
      "tp": 1.095,
      "time": 1733086412,
      "profit": 23.45,
      "comment": "strategy-v1",
      "raw": {...}
    }
  ]
}
```

---

### Cancel Pending Order

**POST /api/v1/orders/removeOrder**

**Body: `RemoveOrderRequest`**

```json
{"ticket": 123456789}
```

Response: `OrderResponse`

---

### Modify Pending Order

**POST /api/v1/orders/updateOrder**

**Query param:** `ticket`

**Body: `UpdateOrderRequest`**

```json
{"price": 1.08600, "sl": 1.08100}
```

Response: `OrderResponse`

---

### Close Position

**POST /api/v1/orders/closePosition**

**Body: `ClosePositionRequest`**

```json
{"ticket": 987654321, "volume": 0.03}
```

Response: `OrderResponse`

---

## Order Types

| Value           | Description                                                | Requirements            |
| --------------- | ---------------------------------------------------------- | ----------------------- |
| BUY             | Market buy at current ask                                  | None                    |
| SELL            | Market sell at current bid                                 | None                    |
| BUY_LIMIT       | Pending buy below market (price < bid - min_distance)      | price                   |
| SELL_LIMIT      | Pending sell above market (price > ask + min_distance)     | price                   |
| BUY_STOP        | Pending buy above market                                   | price                   |
| SELL_STOP       | Pending sell below market                                  | price                   |
| BUY_STOP_LIMIT  | Trigger at stop_limit_price, then limit at price           | price, stop_limit_price |
| SELL_STOP_LIMIT | Trigger at stop_limit_price, then limit at price           | price, stop_limit_price |
| LIMIT           | Smart: auto BUY_LIMIT if below market, SELL_LIMIT if above | price                   |
| MARKET          | Use explicit BUY/SELL instead                              | N/A                     |

* Min distances configurable in MT5Manager (`MIN_DISTANCE_POINTS=2`, `MIN_STOP_DISTANCE_POINTS=10`).
* Market orders respect `deviation` (slippage).

---

## WebSocket – Real-Time Data

**Endpoint:** `ws://<host>:<port>/ws`

* Streams candles and live prices per symbol subscription.
* Interval configurable in JSON: `ws.interval_seconds` (default 1s).
* Payload example (subscribe one symbol, M1 timeframe):

**Client sends subscription list:**

```json
[
  {
    "symbol": "EURUSD",
    "live": true,
    "timeframes": [
      ["M1", 1, true],
      ["H1", 5, false]
    ]
  }
]
```

**Server response:**

```json
[
  {
    "symbol": "EURUSD",
    "live": {"ask": 1.0876, "bid": 1.0874},
    "timeframes": {
      "m1": [
        {"time": 1733086412, "open": 1.085, "high": 1.086, "low": 1.084, "close": 1.0855, "tick_volume": 10}
      ],
      "h1": []
    }
  }
]
```

**Notes:**

* Empty array → no new candle.
* `live` may be `null` if market is closed.
* Multiple symbols/timeframes supported per client.
* Payload always in JSON list format.

---

## Logging & Monitoring

* Daily rotated logs: `./logs/YYYY-MM-DD.log`
* Console output included
* Log level configured via `log_level` in config (`DEBUG`, `INFO`, etc.)
* Timestamps, levels, modules included

---

## Troubleshooting

* MT5 init fails → check path, credentials, terminal running.
* Symbol not found → ensure symbol is selected in MT5.
* Connection issues → increase MT5 timeout.
* Debug → set log_level to `DEBUG`.
* Shutdown → CTRL+C gracefully closes MT5.
