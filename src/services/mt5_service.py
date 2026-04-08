import logging
import threading
from typing import Optional, Dict, Any, List
from datetime import datetime, timezone

try:
    import MetaTrader5 as mt5
except Exception:
    mt5 = None

logger = logging.getLogger(__name__)


class MT5Manager:
    """
    Persistent MT5 manager.
    - Initialize once at app startup (mt5.initialize)
    - Reuse connection for all operations
    - Protect MT5 calls with a reentrant lock
    """
    _instance = None
    _instance_lock = threading.Lock()

    # default distances (in points)
    MIN_DISTANCE_POINTS = 2
    MIN_STOP_DISTANCE_POINTS = 10

    def __init__(self):
        self._lock = threading.RLock()
        self._initialized = False
        self._account_cfg: Optional[Dict[str, Any]] = None
        self.mt5 = mt5

    @classmethod
    def instance(cls) -> "MT5Manager":
        with cls._instance_lock:
            if cls._instance is None:
                cls._instance = MT5Manager()
            return cls._instance

    # -------------------------
    # lifecycle
    # -------------------------
    def initialize(self, account_cfg: Dict[str, Any], mt5_path: Optional[str] = None) -> bool:
        with self._lock:
            if self._initialized:
                logger.info("MT5 already initialized")
                return True

            if mt5 is None:
                logger.error("MetaTrader5 package not available")
                return False

            try:
                path = mt5_path or account_cfg.get("path")
                login = int(account_cfg.get("login"))
                password = account_cfg.get("password")
                server = account_cfg.get("server")

                logger.info("Initializing MT5 terminal. login=%s server=%s", login, server)
                ok = mt5.initialize(path=path, login=login, password=password, server=server, timeout=5000)
                if not ok:
                    err = mt5.last_error() if hasattr(mt5, "last_error") else None
                    logger.error("MT5 initialization failed: %s", err)
                    return False

                self._initialized = True
                self._account_cfg = account_cfg
                logger.info("MT5 initialized successfully (login=%s)", login)
                return True
            except Exception as e:
                logger.exception("Exception initializing MT5: %s", e)
                return False

    def shutdown(self):
        with self._lock:
            if mt5 is None:
                return
            if self._initialized:
                try:
                    logger.info("Shutting down MT5 connection")
                    mt5.shutdown()
                except Exception:
                    logger.exception("Error during MT5 shutdown")
                finally:
                    self._initialized = False

    # -------------------------
    # helpers / utilities
    # -------------------------
    def _now_utc_iso(self) -> str:
        return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

    def _response(self, success: bool, message: str, ticket: Optional[int] = None, details: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        return {
            "success": success,
            "message": message,
            "ticket": int(ticket) if ticket is not None else None,
            "details": details or {}
        }

    def _as_dict_safe(self, obj) -> Dict[str, Any]:
        try:
            return obj._asdict()
        except Exception:
            d = {}
            for k in dir(obj):
                if k.startswith("_"):
                    continue
                try:
                    v = getattr(obj, k)
                    if callable(v):
                        continue
                    d[k] = v
                except Exception:
                    pass
            return d

    def _get_symbol_info_or_select(self, symbol: str):
        info = mt5.symbol_info(symbol)
        if info is None or not getattr(info, "visible", True):
            # try to select it
            try:
                mt5.symbol_select(symbol, True)
            except Exception:
                pass
            info = mt5.symbol_info(symbol)
        return info

    def _get_tick(self, symbol: str):
        return mt5.symbol_info_tick(symbol)

    def _points_to_price(self, symbol_info, points: int) -> float:
        """
        Convert a number of points to a price delta for given symbol.
        """
        point = getattr(symbol_info, "point", None)
        if point is None:
            return float(points) * 0.00001  # fallback guess
        return float(point) * float(points)

    def _compose_comment(self, order_kind: str, symbol: str, client_id: Optional[str], magic: Optional[int], extra: Optional[Dict[str, Any]] = None) -> str:
        """
        Structured comment key=value pairs separated by '|' so clients can parse.
        Includes UTC timestamp (ts_utc).
        Example:
          SDK|ts_utc=2025-10-28T12:05:32Z|type=BUY_LIMIT|symbol=EURUSD|client_id=abc|magic=123|sdk=mt5-rest
        """
        parts = []
        parts.append("SDK")
        parts.append(f"ts_utc={self._now_utc_iso()}")
        parts.append(f"type={order_kind}")
        parts.append(f"symbol={symbol}")
        if client_id:
            parts.append(f"client_id={client_id}")
        if magic:
            parts.append(f"magic={magic}")
        parts.append("sdk=mt5-rest")
        if extra:
            for k, v in extra.items():
                try:
                    parts.append(f"{k}={v}")
                except Exception:
                    pass
        return "|".join(parts)

    def _normalize_mt5_error(self, result_obj) -> Dict[str, Any]:
        """
        Build a helpful error detail dict from MT5 result object or mt5.last_error().
        """
        details = {}
        try:
            if result_obj is not None:
                details.update(self._as_dict_safe(result_obj))
        except Exception:
            pass
        try:
            if hasattr(mt5, "last_error"):
                last = mt5.last_error()
                details["mt5_last_error"] = last
        except Exception:
            pass
        return details

    def _map_kind_to_mt5_const(self, kind: str):
        """
        Map high-level kind string to mt5 constant if present (case-insensitive).
        Returns None if not available.
        """
        k = kind.lower()
        mapping = {
            "buy": getattr(mt5, "ORDER_TYPE_BUY", None),
            "sell": getattr(mt5, "ORDER_TYPE_SELL", None),
            "buy_limit": getattr(mt5, "ORDER_TYPE_BUY_LIMIT", None),
            "sell_limit": getattr(mt5, "ORDER_TYPE_SELL_LIMIT", None),
            "buy_stop": getattr(mt5, "ORDER_TYPE_BUY_STOP", None),
            "sell_stop": getattr(mt5, "ORDER_TYPE_SELL_STOP", None),
            "buy_stop_limit": getattr(mt5, "ORDER_TYPE_BUY_STOP_LIMIT", None),
            "sell_stop_limit": getattr(mt5, "ORDER_TYPE_SELL_STOP_LIMIT", None),
            "market": getattr(mt5, "ORDER_TYPE_BUY", None)  # will handle direction separately
        }
        return mapping.get(k)

    # -------------------------
    # core operations
    # -------------------------
    def place_order(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Place market or pending orders.
        Expected payload keys:
          symbol, volume, order_type (string), price (for pending), sl, tp, deviation, comment, magic, client_id
        Returns standardized dict: {'success', 'message', 'ticket', 'details'}
        """
        with self._lock:
            if not self._initialized:
                return self._response(False, "MT5 not initialized")

            try:
                symbol = payload.get("symbol")
                if not symbol:
                    return self._response(False, "Missing 'symbol'")

                symbol = symbol.upper()
                volume = float(payload.get("volume", 0))
                if volume <= 0:
                    return self._response(False, "Invalid 'volume'")

                order_type_raw = str(payload.get("order_type", "")).upper()
                price = payload.get("price", None)
                stop_limit_price = payload.get("stop_limit_price", None)
                sl = payload.get("sl", 0.0) or 0.0
                tp = payload.get("tp", 0.0) or 0.0
                deviation = int(payload.get("deviation", 10) or 10)
                client_comment = payload.get("comment", "")
                magic = payload.get("magic", None) or self._account_cfg.get("magic") if self._account_cfg else None
                client_id = payload.get("client_id", None)

                # ensure symbol selected/visible
                info = self._get_symbol_info_or_select(symbol)
                if info is None:
                    return self._response(False, f"Symbol not available: {symbol}")

                point = getattr(info, "point", None) or 0.0
                min_distance = float(point) * float(self.MIN_DISTANCE_POINTS)
                min_stop_distance = float(point) * float(self.MIN_STOP_DISTANCE_POINTS)

                # Smart "LIMIT" type: decide BUY_LIMIT vs SELL_LIMIT using ask/bid and min_distance
                if order_type_raw in ("LIMIT",):
                    if price is None:
                        return self._response(False, "Price required for LIMIT type")
                    tick = self._get_tick(symbol)
                    if tick is None:
                        return self._response(False, "Failed to fetch market prices for LIMIT interpretation")
                    ask = float(getattr(tick, "ask", 0.0))
                    bid = float(getattr(tick, "bid", 0.0))

                    # If price >= ask + min_distance -> SELL_LIMIT
                    # If price <= bid - min_distance -> BUY_LIMIT
                    # If price inside [bid - min_distance, ask + min_distance) or inside spread -> reject
                    if price >= ask + min_distance:
                        chosen_kind = "SELL_LIMIT"
                    elif price <= bid - min_distance:
                        chosen_kind = "BUY_LIMIT"
                    else:
                        return self._response(False, "Price too close to market (inside spread) for smart LIMIT order")
                    mt5_kind = getattr(mt5, f"ORDER_TYPE_{chosen_kind}", None)
                    chosen_kind_str = chosen_kind
                else:
                    # user explicitly provided type
                    # special-case explicit MARKET: need direction (buy/sell). For MARKET we expect explicit 'order_type' as BUY/SELL
                    mt5_kind = self._map_kind_to_mt5_const(order_type_raw)
                    chosen_kind_str = order_type_raw
                    if mt5_kind is None:
                        return self._response(False, f"Unsupported or unavailable order_type: {order_type_raw}")

                # Determine whether it's market or pending
                is_market = mt5_kind in (getattr(mt5, "ORDER_TYPE_BUY", None), getattr(mt5, "ORDER_TYPE_SELL", None)) and order_type_raw in ("BUY", "SELL", "MARKET")

                # If it's market but user set order_type to "MARKET", we need a direction field; prefer explicit BUY/SELL
                if order_type_raw == "MARKET":
                    return self._response(False, "Use explicit BUY or SELL for MARKET orders")

                # If it's a pending order and price missing -> error
                if not is_market and price is None:
                    return self._response(False, "Pending orders require 'price'")

                # Additional validations: stop/limit distances
                if sl:
                    # SL distance from price must be >= min_stop_distance
                    # For market orders, compare to current price; for pending use entry price
                    base_price = price if not is_market else (float(getattr(self._get_tick(symbol), "ask")) if mt5_kind == getattr(mt5, "ORDER_TYPE_BUY", None) else float(getattr(self._get_tick(symbol), "bid")))
                    if abs(base_price - float(sl)) < min_stop_distance:
                        return self._response(False, f"SL too close to entry (min distance {min_stop_distance} price units)")

                if tp:
                    base_price = price if not is_market else (float(getattr(self._get_tick(symbol), "ask")) if mt5_kind == getattr(mt5, "ORDER_TYPE_BUY", None) else float(getattr(self._get_tick(symbol), "bid")))
                    if abs(float(tp) - base_price) < min_stop_distance:
                        return self._response(False, f"TP too close to entry (min distance {min_stop_distance} price units)")

                # Compose structured comment: will include UTC timestamp and client data
                extra_comment_fields = {}
                if client_comment:
                    extra_comment_fields["cmsg"] = client_comment[:64]  # shorten client comment to avoid very long comments
                # comment = self._compose_comment(chosen_kind_str, symbol, client_id, magic, extra_comment_fields)
                comment = payload.get("comment") or ""

                # Build request payload for mt5.order_send
                action = mt5.TRADE_ACTION_DEAL if is_market else mt5.TRADE_ACTION_PENDING
                # For market orders, use IOC filling mode (more compatible with brokers)
                type_filling = getattr(mt5, "ORDER_FILLING_IOC", getattr(mt5, "ORDER_FILLING_FOK", getattr(mt5, "ORDER_FILLING_RETURN", 0))) if is_market else getattr(mt5, "ORDER_FILLING_RETURN", 0)
                request = {
                    "action": action,
                    "symbol": symbol,
                    "volume": float(volume),
                    "type": mt5_kind,
                    "price": float(price) if price is not None else 0.0,
                    "sl": float(sl) if sl else 0.0,
                    "tp": float(tp) if tp else 0.0,
                    "deviation": int(deviation),
                    "magic": int(magic) if magic else 0,
                    "comment": comment,
                    "type_filling": type_filling,
                    "type_time": getattr(mt5, "ORDER_TIME_GTC", 0),
                }

                logger.debug("MT5 order_send request: %s", request)
                result = mt5.order_send(request)
                if result is None:
                    details = {}
                    if hasattr(mt5, "last_error"):
                        details["mt5_last_error"] = mt5.last_error()
                    return self._response(False, "order_send returned None", details=details)

                # Build response based on retcode and result fields
                retcode = getattr(result, "retcode", None)
                order_ticket = getattr(result, "order", None) or getattr(result, "request_id", None)

                # common success code constant
                TRADE_RETCODE_DONE = getattr(mt5, "TRADE_RETCODE_DONE", None)
                ok = False
                if TRADE_RETCODE_DONE is not None:
                    ok = (retcode == TRADE_RETCODE_DONE)
                else:
                    # fallback: if result.order is present and >0 assume success
                    ok = bool(order_ticket)

                if not ok:
                    details = self._normalize_mt5_error(result)
                    msg = f"Order failed (retcode={retcode}, comment={getattr(result, 'comment', None)})"
                    return self._response(False, msg, ticket=order_ticket, details=details)

                details = self._as_dict_safe(result)
                return self._response(True, "Order placed", ticket=order_ticket, details=details)

            except Exception as e:
                logger.exception("place_order exception: %s", e)
                return self._response(False, f"Exception: {str(e)}")

    def get_open_orders(self, symbol: Optional[str] = None) -> Dict[str, Any]:
        with self._lock:
            if not self._initialized:
                return self._response(False, "MT5 not initialized")
            try:
                orders = mt5.orders_get(symbol=symbol) if symbol else mt5.orders_get()
                if orders is None:
                    details = {}
                    if hasattr(mt5, "last_error"):
                        details["mt5_last_error"] = mt5.last_error()
                    return self._response(False, "orders_get returned None", details=details)

                out = []
                for o in orders:
                    d = self._as_dict_safe(o)
                    ticket = d.get("ticket") or d.get("order")
                    out.append({
                        "ticket": int(ticket) if ticket else None,
                        "symbol": d.get("symbol"),
                        "type": d.get("type"),
                        "price": float(d.get("price_open") or d.get("price") or 0.0),
                        "volume": float(d.get("volume") or d.get("volume_initial") or 0.0),
                        "sl": d.get("sl"),
                        "tp": d.get("tp"),
                        "time_setup": d.get("time_setup") or d.get("time"),
                        "comment": d.get("comment"),
                        "raw": d
                    })
                return {"success": True, "message": "Open orders retrieved", "orders": out}
            except Exception as e:
                logger.exception("get_open_orders exception: %s", e)
                return self._response(False, f"Exception: {str(e)}")

    def get_open_positions(self, symbol: Optional[str] = None) -> Dict[str, Any]:
        with self._lock:
            if not self._initialized:
                return self._response(False, "MT5 not initialized")
            try:
                positions = mt5.positions_get(symbol=symbol) if symbol else mt5.positions_get()
                if positions is None:
                    details = {}
                    if hasattr(mt5, "last_error"):
                        details["mt5_last_error"] = mt5.last_error()
                    return self._response(False, "positions_get returned None", details=details)

                out = []
                for p in positions:
                    d = self._as_dict_safe(p)
                    ticket = d.get("ticket") or d.get("position")
                    out.append({
                        "ticket": int(ticket) if ticket else None,
                        "symbol": d.get("symbol"),
                        "type": d.get("type"),
                        "volume": float(d.get("volume") or 0.0),
                        "price_open": float(d.get("price_open") or d.get("price") or 0.0),
                        "sl": d.get("sl"),
                        "tp": d.get("tp"),
                        "time": d.get("time"),
                        "profit": d.get("profit"),
                        "comment": d.get("comment") if "comment" in d else None,
                        "raw": d
                    })
                return {"success": True, "message": "Open positions retrieved", "positions": out}
            except Exception as e:
                logger.exception("get_open_positions exception: %s", e)
                return self._response(False, f"Exception: {str(e)}")

    def get_account_info(self) -> Dict[str, Any]:
        """Get account balance, equity, margin info."""
        with self._lock:
            if not self._initialized:
                return self._response(False, "MT5 not initialized")
            try:
                account = mt5.account_info()
                if account is None:
                    details = {}
                    if hasattr(mt5, "last_error"):
                        details["mt5_last_error"] = mt5.last_error()
                    return self._response(False, "account_info returned None", details=details)

                a = self._as_dict_safe(account)
                return {
                    "success": True,
                    "message": "Account info retrieved",
                    "login": a.get("login"),
                    "name": a.get("name"),
                    "server": a.get("server"),
                    "currency": a.get("currency"),
                    "balance": a.get("balance"),
                    "equity": a.get("equity"),
                    "margin": a.get("margin"),
                    "margin_free": a.get("margin_free"),
                    "margin_level": a.get("margin_level"),
                    "profit": a.get("profit"),
                    "leverage": a.get("leverage"),
                    "credit": a.get("credit"),
                }
            except Exception as e:
                logger.exception("get_account_info exception: %s", e)
                return self._response(False, f"Exception: {str(e)}")

    def modify_order(self, ticket: int, update_payload: Dict[str, Any]) -> Dict[str, Any]:
        with self._lock:
            if not self._initialized:
                return self._response(False, "MT5 not initialized")
            try:
                # Retrieve all open orders and find matching ticket
                all_orders = mt5.orders_get()
                if all_orders is None:
                    details = {}
                    if hasattr(mt5, "last_error"):
                        details["mt5_last_error"] = mt5.last_error()
                    return self._response(False, "orders_get returned None", details=details)

                order_obj = None
                for o in all_orders:
                    d = self._as_dict_safe(o)
                    t = d.get("ticket") or d.get("order")
                    if t == ticket:
                        order_obj = o
                        break

                if order_obj is None:
                    return self._response(False, f"Order {ticket} not found")

                od = self._as_dict_safe(order_obj)
                symbol = od.get("symbol")
                new_price = update_payload.get("price", od.get("price_open") or od.get("price"))
                new_sl = update_payload.get("sl", od.get("sl") or 0.0)
                new_tp = update_payload.get("tp", od.get("tp") or 0.0)

                request = {
                    "action": mt5.TRADE_ACTION_MODIFY,
                    "order": int(ticket),
                    "symbol": symbol,
                    "price": float(new_price),
                    "sl": float(new_sl) if new_sl else 0.0,
                    "tp": float(new_tp) if new_tp else 0.0,
                }
                logger.debug("modify_order request: %s", request)
                result = mt5.order_send(request)
                if result is None:
                    details = {}
                    if hasattr(mt5, "last_error"):
                        details["mt5_last_error"] = mt5.last_error()
                    return self._response(False, "order_send returned None during modify", details=details)

                retcode = getattr(result, "retcode", None)
                TRADE_RETCODE_DONE = getattr(mt5, "TRADE_RETCODE_DONE", None)
                if TRADE_RETCODE_DONE is not None and retcode != TRADE_RETCODE_DONE:
                    details = self._normalize_mt5_error(result)
                    return self._response(False, f"Modify failed (retcode={retcode})", ticket=ticket, details=details)

                return self._response(True, "Order modified", ticket=ticket, details=self._as_dict_safe(result))

            except Exception as e:
                logger.exception("modify_order exception: %s", e)
                return self._response(False, f"Exception: {str(e)}")

    def cancel_order(self, ticket: int) -> Dict[str, Any]:
        with self._lock:
            if not self._initialized:
                return self._response(False, "MT5 not initialized")
            try:
                all_orders = mt5.orders_get()
                if all_orders is None:
                    details = {}
                    if hasattr(mt5, "last_error"):
                        details["mt5_last_error"] = mt5.last_error()
                    return self._response(False, "orders_get returned None", details=details)

                order_obj = None
                for o in all_orders:
                    d = self._as_dict_safe(o)
                    t = d.get("ticket") or d.get("order")
                    if t == ticket:
                        order_obj = o
                        break

                if order_obj is None:
                    return self._response(False, f"Order {ticket} not found")

                od = self._as_dict_safe(order_obj)
                symbol = od.get("symbol")
                price = od.get("price_open") or od.get("price") or 0.0

                request = {
                    "action": mt5.TRADE_ACTION_REMOVE,
                    "order": int(ticket),
                    "symbol": symbol,
                    "price": float(price)
                }
                logger.debug("cancel_order request: %s", request)
                result = mt5.order_send(request)
                if result is None:
                    details = {}
                    if hasattr(mt5, "last_error"):
                        details["mt5_last_error"] = mt5.last_error()
                    return self._response(False, "order_send returned None during cancel", details=details)

                retcode = getattr(result, "retcode", None)
                TRADE_RETCODE_DONE = getattr(mt5, "TRADE_RETCODE_DONE", None)
                if TRADE_RETCODE_DONE is not None and retcode != TRADE_RETCODE_DONE:
                    details = self._normalize_mt5_error(result)
                    return self._response(False, f"Cancel failed (retcode={retcode})", ticket=ticket, details=details)

                return self._response(True, "Order canceled", ticket=ticket, details=self._as_dict_safe(result))

            except Exception as e:
                logger.exception("cancel_order exception: %s", e)
                return self._response(False, f"Exception: {str(e)}")

    def modify_position(self, ticket: int, update_payload: Dict[str, Any]) -> Dict[str, Any]:
        """Modify stop loss and take profit for an open position."""
        with self._lock:
            if not self._initialized:
                return self._response(False, "MT5 not initialized")
            try:
                # Retrieve all open positions and find matching ticket
                positions = mt5.positions_get()
                if positions is None:
                    details = {}
                    if hasattr(mt5, "last_error"):
                        details["mt5_last_error"] = mt5.last_error()
                    return self._response(False, "positions_get returned None", details=details)

                position_obj = None
                for p in positions:
                    d = self._as_dict_safe(p)
                    t = d.get("ticket") or d.get("position")
                    if t == ticket:
                        position_obj = p
                        break

                if position_obj is None:
                    return self._response(False, f"Position {ticket} not found")

                pd = self._as_dict_safe(position_obj)
                symbol = pd.get("symbol")
                new_sl = update_payload.get("sl", pd.get("sl") or 0.0)
                new_tp = update_payload.get("tp", pd.get("tp") or 0.0)
                comment = update_payload.get("comment", "")

                request = {
                    "action": mt5.TRADE_ACTION_SLTP,
                    "position": int(ticket),
                    "symbol": symbol,
                    "sl": float(new_sl) if new_sl else 0.0,
                    "tp": float(new_tp) if new_tp else 0.0,
                    "comment": comment,
                }
                logger.debug("modify_position request: %s", request)
                result = mt5.order_send(request)
                if result is None:
                    details = {}
                    if hasattr(mt5, "last_error"):
                        details["mt5_last_error"] = mt5.last_error()
                    return self._response(False, "order_send returned None during modify", details=details)

                retcode = getattr(result, "retcode", None)
                TRADE_RETCODE_DONE = getattr(mt5, "TRADE_RETCODE_DONE", None)
                if TRADE_RETCODE_DONE is not None and retcode != TRADE_RETCODE_DONE:
                    details = self._normalize_mt5_error(result)
                    return self._response(False, f"Modify failed (retcode={retcode})", ticket=ticket, details=details)

                return self._response(True, "Position modified", ticket=ticket, details=self._as_dict_safe(result))

            except Exception as e:
                logger.exception("modify_position exception: %s", e)
                return self._response(False, f"Exception: {str(e)}")

    def close_position(self, ticket: int, volume: Optional[float] = None) -> Dict[str, Any]:
        with self._lock:
            if not self._initialized:
                return self._response(False, "MT5 not initialized")
            try:
                positions = mt5.positions_get()
                if positions is None:
                    details = {}
                    if hasattr(mt5, "last_error"):
                        details["mt5_last_error"] = mt5.last_error()
                    return self._response(False, "positions_get returned None", details=details)

                pos_obj = None
                for p in positions:
                    d = self._as_dict_safe(p)
                    t = d.get("ticket") or d.get("position")
                    if t == ticket:
                        pos_obj = p
                        break

                if pos_obj is None:
                    return self._response(False, f"Position {ticket} not found")

                pd = self._as_dict_safe(pos_obj)
                symbol = pd.get("symbol")
                pos_type = pd.get("type")  # numeric constant typically
                current_volume = float(pd.get("volume") or 0.0)
                close_volume = float(volume) if volume else current_volume
                if close_volume <= 0 or close_volume > current_volume:
                    return self._response(False, "Invalid close volume")

                # determine order type opposite to current (closing)
                buy_type = getattr(mt5, "ORDER_TYPE_BUY", None)
                sell_type = getattr(mt5, "ORDER_TYPE_SELL", None)
                if pos_type == buy_type:
                    order_type = sell_type
                else:
                    order_type = buy_type

                # choose price (ask/bid)
                tick = self._get_tick(symbol)
                if tick is None:
                    return self._response(False, "Failed to get tick for closing")

                price = float(getattr(tick, "bid")) if order_type == sell_type else float(getattr(tick, "ask"))

                request = {
                    "action": mt5.TRADE_ACTION_DEAL,
                    "symbol": symbol,
                    "volume": close_volume,
                    "type": order_type,
                    "position": int(ticket),
                    "price": price,
                    "deviation": 10,
                    "magic": int(self._account_cfg.get("magic", 123456)) if self._account_cfg else 123456,
                    "comment": f"SDK|ts_utc={self._now_utc_iso()}|action=close|position={ticket}",
                    "type_filling": getattr(mt5, "ORDER_FILLING_RETURN", getattr(mt5, "ORDER_FILLING_IOC", 0)),
                }

                logger.debug("close_position request: %s", request)
                result = mt5.order_send(request)
                if result is None:
                    details = {}
                    if hasattr(mt5, "last_error"):
                        details["mt5_last_error"] = mt5.last_error()
                    return self._response(False, "order_send returned None during close", details=details)

                retcode = getattr(result, "retcode", None)
                TRADE_RETCODE_DONE = getattr(mt5, "TRADE_RETCODE_DONE", None)
                if TRADE_RETCODE_DONE is not None and retcode != TRADE_RETCODE_DONE:
                    details = self._normalize_mt5_error(result)
                    return self._response(False, f"Close failed (retcode={retcode})", ticket=ticket, details=details)

                return self._response(True, "Position closed", ticket=ticket, details=self._as_dict_safe(result))

            except Exception as e:
                logger.exception("close_position exception: %s", e)
                return self._response(False, f"Exception: {str(e)}")


# module-level singleton
mt5_manager = MT5Manager.instance()
