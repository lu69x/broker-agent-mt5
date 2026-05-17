"""MT5 Terminal Connector

Handles connection to MetaTrader 5 Terminal and data retrieval.
"""
from datetime import datetime
from typing import List, Dict, Any, Optional

try:
    import MetaTrader5 as mt5
except ImportError:
    mt5 = None

from .logger import get_logger

logger = get_logger(__name__)


class MT5Connector:
    """Connector for MetaTrader 5 Terminal."""

    def __init__(self, config: dict):
        self.config = config.get("mt5", {})
        self.login = self.config.get("login", 0)
        self.password = self.config.get("password", "")
        self.server = self.config.get("server", "")
        self.timeout = self.config.get("timeout", 60000)
        self._connected = False

    def connect(self) -> bool:
        """Connect to MT5 Terminal."""
        if mt5 is None:
            logger.error("MetaTrader5 package not installed")
            return False

        logger.info("Connecting to MT5 Terminal...")

        # Initialize MT5
        if not mt5.initialize():
            error = mt5.last_error()
            logger.error(f"MT5 initialize failed: {error}")
            return False

        # Login if credentials provided
        if self.login > 0:
            if not mt5.login(self.login, self.password, self.server):
                error = mt5.last_error()
                logger.error(f"MT5 login failed: {error}")
                mt5.shutdown()
                return False
            logger.info(f"Logged in as {self.login}@{self.server}")
        else:
            # Use existing terminal connection
            account = mt5.account_info()
            if account is None:
                logger.error("No active MT5 terminal connection")
                mt5.shutdown()
                return False
            logger.info(f"Using existing connection: {account.login}@{account.server}")

        self._connected = True
        logger.info("MT5 Terminal connected")
        return True

    def disconnect(self):
        """Disconnect from MT5 Terminal."""
        if self._connected:
            mt5.shutdown()
            self._connected = False
            logger.info("MT5 Terminal disconnected")

    @property
    def connected(self) -> bool:
        """Check if connected to MT5."""
        return self._connected and mt5 and mt5.terminal_info() is not None

    @staticmethod
    def _to_unix_ts(value: Any) -> int:
        """Convert MT5 time-like values to unix seconds safely."""
        if value is None:
            return 0
        if isinstance(value, datetime):
            return int(value.timestamp())
        if isinstance(value, (int, float)):
            return int(value)
        if hasattr(value, "timestamp"):
            try:
                return int(value.timestamp())
            except Exception:
                return 0
        return 0

    def get_account(self) -> Optional[Dict[str, Any]]:
        """Get account information."""
        if not self.connected:
            return None

        account = mt5.account_info()
        if account is None:
            return None

        return {
            "login": account.login,
            "leverage": account.leverage,
            "balance": account.balance,
            "equity": account.equity,
            "margin": account.margin,
            "margin_free": account.margin_free,
            "margin_level": account.margin_level,
            "profit": account.profit,
            "currency": account.currency,
            "server": account.server,
            "company": account.company,
            "trade_allowed": account.trade_allowed,
            "trade_expert": account.trade_expert,
            "limit_orders": account.limit_orders,
            "margin_so_call": account.margin_so_call,
            "margin_so_so": account.margin_so_so,
            "currency_digits": account.currency_digits,
        }

    def get_positions(self) -> List[Dict[str, Any]]:
        """Get open positions."""
        if not self.connected:
            return []

        positions = mt5.positions_get()
        if positions is None:
            return []

        return [
            {
                "ticket": pos.ticket,
                "symbol": pos.symbol,
                "type": pos.type,
                "volume": pos.volume,
                "price_open": pos.price_open,
                "price_current": pos.price_current,
                "sl": pos.sl,
                "tp": pos.tp,
                "swap": pos.swap,
                "profit": pos.profit,
                "comment": pos.comment,
                "magic": pos.magic,
                "time": self._to_unix_ts(pos.time),
                "time_update": self._to_unix_ts(pos.time_update),
            }
            for pos in positions
        ]

    def get_balances(self) -> List[Dict[str, Any]]:
        """Get balances in broker_service-compatible shape."""
        account = self.get_account()
        if not account:
            return []
        asset = account.get("currency", "") or "USD"
        free = float(account.get("margin_free", 0.0))
        locked = float(account.get("margin", 0.0))
        total = float(account.get("balance", 0.0))
        return [{
            "asset": asset,
            "free": free,
            "locked": locked,
            "total": total,
        }]

    def get_orders(self) -> List[Dict[str, Any]]:
        """Get open orders."""
        if not self.connected:
            return []

        orders = mt5.orders_get()
        if orders is None:
            return []

        return [
            {
                "ticket": order.ticket,
                "symbol": order.symbol,
                "type": order.type,
                "state": order.state,
                "volume_initial": order.volume_initial,
                "volume_current": order.volume_current,
                "price_open": order.price_open,
                "sl": order.sl,
                "tp": order.tp,
                "magic": order.magic,
                "comment": order.comment,
                "time_setup": self._to_unix_ts(order.time_setup),
                "time_done": 0,  # Open orders have no time_done
            }
            for order in orders
        ]

    def get_history_orders(self, symbol: str = "", from_date: Optional[datetime] = None, to_date: Optional[datetime] = None) -> List[Dict[str, Any]]:
        """Get history orders."""
        if not self.connected:
            return []

        if from_date is None:
            from_date = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        if to_date is None:
            to_date = datetime.now()

        orders = mt5.history_orders_get(from_date, to_date, symbol=symbol if symbol else None)
        if orders is None:
            return []

        return [
            {
                "ticket": order.ticket,
                "symbol": order.symbol,
                "type": order.type,
                "state": order.state,
                "volume_initial": order.volume_initial,
                "volume_current": order.volume_current,
                "price_open": order.price_open,
                "sl": order.sl,
                "tp": order.tp,
                "magic": order.magic,
                "comment": order.comment,
                "time_setup": self._to_unix_ts(order.time_setup),
                "time_done": self._to_unix_ts(order.time_done),
            }
            for order in orders
        ]

    def get_symbol_tick(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Get symbol tick."""
        if not self.connected:
            return None

        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            return None

        return {
            "time": self._to_unix_ts(tick.time),
            "bid": tick.bid,
            "ask": tick.ask,
            "last": tick.last,
            "volume": tick.volume,
            "time_msc": tick.time_msc,
            "flags": tick.flags,
            "volume_real": tick.volume_real,
        }

    def get_symbol_info(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Get symbol information."""
        if not self.connected:
            return None

        info = mt5.symbol_info(symbol)
        if info is None:
            return None

        return {
            "symbol": info.name,
            "description": info.description,
            "currency_base": info.currency_base,
            "currency_profit": info.currency_profit,
            "digits": info.digits,
            "point": info.point,
            "volume_min": info.volume_min,
            "volume_max": info.volume_max,
            "volume_step": info.volume_step,
            "visible": info.visible,
        }

    def get_rates(self, symbol: str, timeframe: str, count: int = 100) -> List[Dict[str, Any]]:
        """Get OHLCV rates."""
        if not self.connected:
            return []

        # Map timeframe string to MT5 constant
        tf_map = {
            "M1": mt5.TIMEFRAME_M1,
            "M5": mt5.TIMEFRAME_M5,
            "M15": mt5.TIMEFRAME_M15,
            "M30": mt5.TIMEFRAME_M30,
            "H1": mt5.TIMEFRAME_H1,
            "H4": mt5.TIMEFRAME_H4,
            "D1": mt5.TIMEFRAME_D1,
        }
        tf = tf_map.get(timeframe, mt5.TIMEFRAME_M1)

        rates = mt5.copy_rates_from_pos(symbol, tf, 0, count)
        if rates is None:
            return []

        return [
            {
                "time": int(rate["time"]),
                "open": rate["open"],
                "high": rate["high"],
                "low": rate["low"],
                "close": rate["close"],
                "tick_volume": rate["tick_volume"],
                "spread": rate["spread"],
                "real_volume": rate["real_volume"],
            }
            for rate in rates
        ]

    def order_send(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Send trade order via MT5 order_send()."""
        if not self.connected:
            return {}
        req = dict(payload or {})
        symbol = str(req.get("symbol", "") or "").upper()

        # Normalize numeric fields.
        if "volume" in req:
            req["volume"] = float(req.get("volume") or 0.0)
        if "price" in req:
            req["price"] = float(req.get("price") or 0.0)
        if "type" in req:
            req["type"] = int(req.get("type") or 0)
        if "action" in req:
            req["action"] = int(req.get("action") or 0)
        if "position" in req:
            req["position"] = int(req.get("position") or 0)
        if "order" in req:
            req["order"] = int(req.get("order") or 0)

        # Close-by-position flow for hedging accounts.
        # Apply only for market deal actions; SL/TP updates also carry "position".
        if int(req.get("position") or 0) > 0 and int(req.get("action") or 0) == int(getattr(mt5, "TRADE_ACTION_DEAL", 1)):
            pos_id = int(req.get("position"))
            positions = mt5.positions_get(ticket=pos_id) or []
            if not positions:
                all_pos = mt5.positions_get() or []
                tickets = [int(getattr(p, "ticket", 0) or 0) for p in all_pos]
                logger.error(f"close by position failed: ticket {pos_id} not found, open_tickets={tickets}")
                return {
                    "retcode": -1,
                    "deal": 0,
                    "order": 0,
                    "volume": 0.0,
                    "price": 0.0,
                    "bid": 0.0,
                    "ask": 0.0,
                    "comment": f"position ticket not found: {pos_id}",
                    "request_id": 0,
                    "retcode_external": 0,
                }

            pos = positions[0]
            symbol = str(getattr(pos, "symbol", "") or "").upper()
            if symbol:
                try:
                    mt5.symbol_select(symbol, True)
                except Exception:
                    pass

            pos_type = int(getattr(pos, "type", 0) or 0)
            close_type = mt5.ORDER_TYPE_SELL if pos_type == mt5.POSITION_TYPE_BUY else mt5.ORDER_TYPE_BUY
            tick = mt5.symbol_info_tick(symbol) if symbol else None
            close_price = 0.0
            if tick is not None:
                close_price = float(tick.bid if close_type == mt5.ORDER_TYPE_SELL else tick.ask)

            req = {
                "action": mt5.TRADE_ACTION_DEAL,
                "symbol": symbol,
                "volume": float(req.get("volume") or getattr(pos, "volume", 0.0) or 0.0),
                "type": int(close_type),
                "position": int(getattr(pos, "ticket", 0) or 0),
                "price": close_price,
                "deviation": int(req.get("deviation") or 20),
            }

        # Market deal without explicit price is often rejected by brokers.
        if req.get("action") == getattr(mt5, "TRADE_ACTION_DEAL", 1) and float(req.get("price") or 0.0) <= 0:
            tick = mt5.symbol_info_tick(symbol) if symbol else None
            if tick is not None:
                order_type = int(req.get("type") or 0)
                req["price"] = float(tick.ask if order_type == 0 else tick.bid)

        # Safe defaults for execution constraints.
        req.setdefault("deviation", 20)
        if hasattr(mt5, "ORDER_TIME_GTC"):
            req.setdefault("type_time", mt5.ORDER_TIME_GTC)
        if hasattr(mt5, "ORDER_FILLING_IOC"):
            req.setdefault("type_filling", mt5.ORDER_FILLING_IOC)

        symbol = str(req.get("symbol", "") or "").upper()
        if symbol:
            req["symbol"] = symbol

        logger.info(f"order_send request: {req}")
        result = mt5.order_send(req)
        if result is None:
            last_err = mt5.last_error() if hasattr(mt5, "last_error") else ("unknown", "unknown")
            logger.error(f"order_send returned None, last_error={last_err}")
            return {
                "retcode": -1,
                "deal": 0,
                "order": 0,
                "volume": 0.0,
                "price": float(req.get("price") or 0.0),
                "bid": 0.0,
                "ask": 0.0,
                "comment": f"order_send returned None, last_error={last_err}",
                "request_id": 0,
                "retcode_external": 0,
            }
        logger.info(
            "order_send result: retcode=%s comment=%s order=%s deal=%s",
            getattr(result, "retcode", None),
            getattr(result, "comment", None),
            getattr(result, "order", None),
            getattr(result, "deal", None),
        )
        return {
            "retcode": int(getattr(result, "retcode", 0) or 0),
            "deal": int(getattr(result, "deal", 0) or 0),
            "order": int(getattr(result, "order", 0) or 0),
            "volume": float(getattr(result, "volume", 0.0) or 0.0),
            "price": float(getattr(result, "price", 0.0) or 0.0),
            "bid": float(getattr(result, "bid", 0.0) or 0.0),
            "ask": float(getattr(result, "ask", 0.0) or 0.0),
            "comment": str(getattr(result, "comment", "") or ""),
            "request_id": int(getattr(result, "request_id", 0) or 0),
            "retcode_external": int(getattr(result, "retcode_external", 0) or 0),
        }

    def order_check(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Check trade request via MT5 order_check()."""
        if not self.connected:
            return {}
        if not hasattr(mt5, "order_check"):
            return {
                "retcode": 0,
                "balance": 0.0,
                "equity": 0.0,
                "profit": 0.0,
                "margin": 0.0,
                "margin_free": 0.0,
                "margin_level": 0.0,
                "comment": "order_check not available",
            }
        result = mt5.order_check(payload)
        if result is None:
            return {}
        return {
            "retcode": int(getattr(result, "retcode", 0) or 0),
            "balance": float(getattr(result, "balance", 0.0) or 0.0),
            "equity": float(getattr(result, "equity", 0.0) or 0.0),
            "profit": float(getattr(result, "profit", 0.0) or 0.0),
            "margin": float(getattr(result, "margin", 0.0) or 0.0),
            "margin_free": float(getattr(result, "margin_free", 0.0) or 0.0),
            "margin_level": float(getattr(result, "margin_level", 0.0) or 0.0),
            "comment": str(getattr(result, "comment", "") or ""),
        }

    def order_cancel(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Cancel order by sending REMOVE action through order_send()."""
        if not self.connected:
            return {}
        order = int(payload.get("order", 0) or 0)
        symbol = payload.get("symbol", "")
        req = {
            "action": mt5.TRADE_ACTION_REMOVE,
            "order": order,
        }
        if symbol:
            req["symbol"] = symbol
        result = mt5.order_send(req)
        if result is None:
            last_err = mt5.last_error() if hasattr(mt5, "last_error") else ("unknown", "unknown")
            logger.error(f"order_cancel returned None, last_error={last_err}, req={req}")
            return {"retcode": -1, "order": order, "comment": f"order_cancel returned None, last_error={last_err}"}
        return {
            "retcode": int(getattr(result, "retcode", 0) or 0),
            "order": order,
            "comment": str(getattr(result, "comment", "") or ""),
        }
