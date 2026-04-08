import asyncio
import json
import logging
import functools
from typing import Dict, List, Any, Optional
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field, validator, ConfigDict, field_validator, Field

from src.services.mt5_service import mt5_manager
from src.services.chart_service import chart_data_service
from src.config import load_config, detect_live_flag

router = APIRouter()
logger = logging.getLogger(__name__)

_cfg = load_config(use_live=detect_live_flag())  # Or pass live flag if needed
WS_INTERVAL = _cfg.get("ws", {}).get("interval_seconds", 5)

# --- MT5 Constants & Helpers ---
TF_MAP = {
    "M1": 1,
    "M2": 2,
    "M3": 3,
    "M4": 4,
    "M5": 5,
    "M6": 6,
    "M10": 10,
    "M12": 12,
    "M15": 15,
    "M20": 20,
    "M30": 30,
    "H1": 16385,
    "H2": 16386,
    "H3": 16387,
    "H4": 16388,
    "H6": 16390,
    "H8": 16392,
    "H12": 16396,
    "D1": 16408,
    "W1": 32769,
    "MN1": 49153,
}

# --- Pydantic Models for Validation ---


class TimeframeReq(BaseModel):
    name: str
    count: int = 1
    always_send: bool = False

    def __init__(self, **data):
        # Handle the list input: ["m1", 1, true]
        if isinstance(data, list):
            name = data[0]
            count = data[1] if len(data) > 1 else 1
            always_send = data[2] if len(data) > 2 else False
            super().__init__(name=name, count=count, always_send=always_send)
        else:
            super().__init__(**data)


class SymbolSub(BaseModel):
    symbol: str
    live: bool = True
    timeframes: List[Any] = Field(
        default_factory=list
    )  # Use Field for better default list handling

    # --- THE FIX IS HERE ---
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    @field_validator("symbol")  # Use field_validator for Pydantic v2
    @classmethod
    def normalize_symbol(cls, v):
        return v.upper()

    @field_validator(
        "timeframes", mode="before"
    )  # Use field_validator and mode='before'
    @classmethod
    def parse_timeframes(cls, v):
        # Convert list of lists -> List[TimeframeReq]
        parsed = []
        for item in v:
            if isinstance(item, list):
                # Map ["m1", 1, true] -> object
                tf_name = item[0].upper()
                count = item[1] if len(item) > 1 else 1
                # If third element is not present, use False. If present, use its value.
                force = item[2] if len(item) > 2 else False
                parsed.append(
                    TimeframeReq(name=tf_name, count=count, always_send=force)
                )
        return parsed


# --- Async Executor (Performance Fix) ---
async def run_in_executor(func, *args):
    """Run sync MT5 functions in a separate thread to keep asyncio loop non-blocking."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, functools.partial(func, *args))


# --- Sync Worker Functions (Internal) ---
def _fetch_candles_sync(symbol: str, tf_str: str, count: int) -> List[dict]:
    if not mt5_manager._initialized:
        return []

    tf_const = TF_MAP.get(tf_str)
    if not tf_const:
        return []

    # get candles starting from pos 1 (last CLOSED candle)
    rates = mt5_manager.mt5.copy_rates_from_pos(symbol, tf_const, 1, count)

    if rates is None or len(rates) == 0:
        return []

    # Convert numpy array to list of dicts
    result = []
    for bar in rates:
        candle_data = {
            "time": int(bar["time"]),
            "open": float(bar["open"]),
            "high": float(bar["high"]),
            "low": float(bar["low"]),
            "close": float(bar["close"]),
            "tick_volume": int(bar["tick_volume"]),
            # "spread": int(bar['spread']), # Optional, saving bandwidth
            # "real_volume": int(bar['real_volume']) # Optional
        }
        result.append(candle_data)
        
        # Update chart service if this is the default timeframe (H1)
        if tf_str == 'H1' and symbol == 'XAUUSD':
            # Convert to chart service format
            chart_candle = candle_data.copy()
            chart_candle['volume'] = candle_data['tick_volume']
            
            # Add to chart service (it will handle duplicates and indicators)
            try:
                chart_data_service.add_candle(chart_candle)
            except Exception as e:
                logger.error(f"Error adding candle to chart service: {e}")
    
    return result


def _fetch_tick_sync(symbol: str) -> dict | None:
    if not mt5_manager._initialized:
        return None
    tick = mt5_manager.mt5.symbol_info_tick(symbol)
    if not tick:
        return None
    return {"ask": float(tick.ask), "bid": float(tick.bid)}


# --- Connection Manager ---


class ClientState:
    """Stores subscription config + State of what was last sent to this specific client."""

    def __init__(self, config: List[SymbolSub]):
        self.config = config
        # Key: (symbol, timeframe) -> Value: last_candle_time (int)
        self.last_sent_times: Dict[str, int] = {}


class ConnectionManager:
    def __init__(self):
        # Key: WebSocket -> Value: ClientState
        self.active_connections: Dict[WebSocket, ClientState] = {}

    async def connect(self, websocket: WebSocket):
        await websocket.accept()

    def disconnect(self, websocket: WebSocket):
        self.active_connections.pop(websocket, None)

    def set_subscription(self, websocket: WebSocket, sub_data: List[dict]):
        """Parses and stores the subscription model."""
        try:
            # Parse list of dicts into Pydantic models
            parsed_config = [SymbolSub(**item) for item in sub_data]
            self.active_connections[websocket] = ClientState(parsed_config)
            return True
        except Exception as e:
            logger.error(f"Subscription parse error: {e}")
            return False


manager = ConnectionManager()


# --- Main Broadcaster Loop ---


async def initialize_chart_data():
    """Initialize chart service with historical candle data."""
    try:
        if not mt5_manager._initialized:
            logger.warning("MT5 not initialized, skipping chart data initialization")
            return
        
        # Fetch 100 historical candles for XAUUSD H1
        logger.info("Initializing chart service with historical data...")
        historical_candles = await run_in_executor(
            _fetch_candles_sync, 'XAUUSD', 'H1', 100
        )
        
        if historical_candles:
            logger.info(f"Loaded {len(historical_candles)} historical candles for chart")
            # The candles are already added to chart service in _fetch_candles_sync
        else:
            logger.warning("No historical candles available")
            
    except Exception as e:
        logger.error(f"Error initializing chart data: {e}")


async def candle_watcher():
    """Iterates through clients, fetches data based on their specific needs."""
    logger.info("Starting optimized candle watcher (1s interval)...")

    # Initialize chart service with historical data
    await initialize_chart_data()

    while True:
        if not mt5_manager._initialized:
            await asyncio.sleep(WS_INTERVAL)
            continue

        # Iterate over a copy of keys to avoid runtime error if client disconnects mid-loop
        active_sockets = list(manager.active_connections.keys())

        for websocket in active_sockets:
            client_state = manager.active_connections.get(websocket)
            if not client_state:
                continue

            response_payload = []

            for sub in client_state.config:
                symbol = sub.symbol

                # 1. Handle Live Prices
                live_data = None
                if sub.live:
                    live_data = await run_in_executor(_fetch_tick_sync, symbol)

                # 2. Handle Timeframes
                tf_data = {}

                for tf_req in sub.timeframes:
                    # Logic: fetch candles
                    candles = await run_in_executor(
                        _fetch_candles_sync, symbol, tf_req.name, tf_req.count
                    )

                    if not candles:
                        tf_data[tf_req.name.lower()] = []
                        continue

                    last_candle = candles[-1]  # The most recent one in the list
                    last_time = last_candle["time"]

                    # State Key: "EURUSD_H1"
                    state_key = f"{symbol}_{tf_req.name}"
                    prev_time = client_state.last_sent_times.get(state_key, 0)

                    # Logic: Should we include this data?
                    # YES if: always_send is True OR timestamp > prev_timestamp
                    should_send = tf_req.always_send or (last_time > prev_time)

                    if should_send:
                        # Normalize key to lowercase as requested: "m1"
                        tf_data[tf_req.name.lower()] = candles
                        # Update state
                        client_state.last_sent_times[state_key] = last_time
                    else:
                        # Return empty list to indicate "no new data"
                        tf_data[tf_req.name.lower()] = []

                # Build the symbol result object
                symbol_result = {"symbol": symbol, "timeframes": tf_data}

                # Only add 'live' key if the user asked for it (or if it's default)
                if sub.live and live_data:
                    symbol_result["live"] = live_data
                elif sub.live and not live_data:
                    symbol_result["live"] = None  # Market might be closed

                response_payload.append(symbol_result)

            # Send the big JSON payload
            try:
                if response_payload:
                    await websocket.send_text(json.dumps(response_payload))
            except Exception:
                # Socket likely dead, manager.disconnect will handle it eventually
                # but we can force clean up here if we want
                pass

        await asyncio.sleep(WS_INTERVAL)  # 1 second interval


# --- Routes ---


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            try:
                payload = json.loads(data)

                # We expect the payload to be the list directly,
                # OR a dict like {"action": "subscribe", "data": [...]}
                # Let's support your structure: The payload IS the subscription list.

                # If it's a list, assume it's the subscription model
                if isinstance(payload, list):
                    success = manager.set_subscription(websocket, payload)
                    if success:
                        await websocket.send_json({"status": "subscribed"})
                    else:
                        await websocket.send_json(
                            {"error": "Invalid subscription format"}
                        )

                # Fallback for "action" style if you still use it
                elif isinstance(payload, dict) and payload.get("action") == "subscribe":
                    success = manager.set_subscription(
                        websocket, payload.get("data", [])
                    )
                    # ...

            except json.JSONDecodeError:
                await websocket.send_json({"error": "Invalid JSON"})
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"WS Error: {e}")
        manager.disconnect(websocket)
