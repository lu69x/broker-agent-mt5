"""MT5 Broker Agent - Main Agent Class

Orchestrates MT5 connection and reverse-stream gRPC communication.
"""
import asyncio
import time
from datetime import datetime, timezone

from .mt5_connector import MT5Connector
from .grpc_client import BrokerClient
from .logger import get_logger

logger = get_logger(__name__)


class MT5Agent:
    """Main MT5 Broker Agent."""

    def __init__(self, config: dict):
        self.config = config
        self.agent_config = config.get("agent", {})
        self.collection_config = config.get("collection", {})

        self.agent_id = self.agent_config.get("id", "agent-001")
        self.agent_name = self.agent_config.get("name", "MT5 Agent")
        self.heartbeat_interval = self.agent_config.get("heartbeat_interval", 30)
        self.lease_seconds = self.agent_config.get("lease_seconds", 60)
        self.auth_wait_timeout = self.agent_config.get("auth_wait_timeout", 60)

        self.mt5 = MT5Connector(config)
        self.broker = BrokerClient(config)

        self._running = False
        self._tasks = []

    async def start(self):
        """Start the agent."""
        logger.info("Starting MT5 Agent...")

        if not self.mt5.connect():
            logger.error("Failed to connect to MT5 Terminal")
            raise RuntimeError("MT5 connection failed")

        if not self.broker.connect():
            logger.error("Failed to connect to Broker Service")
            self.mt5.disconnect()
            raise RuntimeError("Broker connection failed")

        result = self.broker.start_reverse_stream(
            agent_id=self.agent_id,
            agent_name=self.agent_name,
            lease_seconds=self.lease_seconds,
            startup_timeout=self.auth_wait_timeout,
            command_handler=self._handle_command,
        )
        if not result.get("success"):
            self.broker.disconnect()
            self.mt5.disconnect()
            raise RuntimeError(f"Reverse stream setup failed: {result.get('error')}")

        logger.info("Reverse stream connected")
        self._running = True
        self._tasks = [
            asyncio.create_task(self._heartbeat_loop()),
            asyncio.create_task(self._stream_watchdog_loop()),
        ]

    async def stop(self):
        """Stop the agent."""
        if not self._running:
            return

        logger.info("Stopping MT5 Agent...")
        self._running = False

        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)

        self.broker.disconnect()
        self.mt5.disconnect()

    async def run(self):
        """Run agent until stopped."""
        while self._running:
            await asyncio.sleep(1)

    async def _heartbeat_loop(self):
        """Send periodic heartbeats on reverse stream."""
        while self._running:
            try:
                self.broker.send_heartbeat(lease_seconds=self.lease_seconds)
            except Exception as e:
                logger.error(f"Heartbeat error: {e}")
            await asyncio.sleep(self.heartbeat_interval)

    async def _stream_watchdog_loop(self):
        """Stop agent when reverse stream is lost."""
        while self._running:
            if not self.broker.stream_alive():
                err = self.broker.get_last_error() or "stream closed"
                logger.error(f"Reverse stream disconnected: {err}")
                self._running = False
                break
            await asyncio.sleep(1)

    def _handle_command(self, command_type: str, payload: dict) -> tuple[bool, dict, str]:
        """Dispatch broker command to MT5 connector and return serializable result."""
        try:
            if command_type == "GetAccountInfo":
                account = self.mt5.get_account()
                if not account:
                    return False, {}, "mt5 account is not available"
                return True, account, ""

            if command_type == "GetPositions":
                symbol = (payload.get("symbol") or "").strip().upper()
                positions = self.mt5.get_positions()
                if symbol:
                    positions = [p for p in positions if (p.get("symbol", "").upper() == symbol)]
                return True, {"positions": positions}, ""

            if command_type == "GetBalances":
                return True, {"balances": self.mt5.get_balances()}, ""

            if command_type == "GetSymbolInfo":
                symbol = (payload.get("symbol") or "").strip().upper()
                if not symbol:
                    return False, {}, "symbol is required"
                info = self.mt5.get_symbol_info(symbol)
                if not info:
                    return False, {}, f"symbol info is not available for {symbol}"
                return True, info, ""

            if command_type == "GetSymbolTick":
                symbol = (payload.get("symbol") or "").strip().upper()
                if not symbol:
                    return False, {}, "symbol is required"
                tick = self.mt5.get_symbol_tick(symbol)
                if not tick:
                    return False, {}, f"symbol tick is not available for {symbol}"
                return True, tick, ""

            if command_type == "GetRatesRange":
                symbol = (payload.get("symbol") or "").strip().upper()
                timeframe = (payload.get("timeframe") or "").strip().upper()
                if not symbol:
                    return False, {}, "symbol is required"
                if not timeframe:
                    return False, {}, "timeframe is required"
                from_ts = int(payload.get("from") or 0)
                to_ts = int(payload.get("to") or 0)
                count = 100
                if from_ts > 0 and to_ts > 0 and to_ts > from_ts:
                    count = min(5000, max(1, int((to_ts - from_ts) / 60)))
                rates = self.mt5.get_rates(symbol, timeframe, count=count)
                return True, {"values": rates}, ""

            if command_type == "GetOpenOrders":
                symbol = (payload.get("symbol") or "").strip().upper()
                orders = self.mt5.get_orders()
                if symbol:
                    orders = [o for o in orders if (o.get("symbol", "").upper() == symbol)]
                return True, {"orders": orders}, ""

            if command_type == "GetHistoryOrders":
                symbol = (payload.get("symbol") or "").strip().upper()
                req_from = int(payload.get("from") or 0)
                req_to = int(payload.get("to") or 0)
                from_dt = datetime.fromtimestamp(req_from, tz=timezone.utc) if req_from else None
                to_dt = datetime.fromtimestamp(req_to, tz=timezone.utc) if req_to else None
                orders = self.mt5.get_history_orders(symbol=symbol, from_date=from_dt, to_date=to_dt)
                return True, {"orders": orders}, ""

            if command_type == "OrderCheck":
                result = self.mt5.order_check(payload)
                if not result:
                    return False, {}, "mt5 order_check failed"
                return True, result, ""

            if command_type == "OrderSend":
                result = self.mt5.order_send(payload)
                if not result:
                    return False, {}, "mt5 order_send failed"
                retcode = int(result.get("retcode", 0) or 0)
                if not self._trade_retcode_ok(retcode):
                    return False, result, f"order_send failed retcode={retcode} comment={result.get('comment', '')}"
                return True, result, ""

            if command_type == "OrderCancel":
                result = self.mt5.order_cancel(payload)
                if not result:
                    return False, {}, "mt5 order_cancel failed"
                retcode = int(result.get("retcode", 0) or 0)
                if not self._trade_retcode_ok(retcode):
                    return False, result, f"order_cancel failed retcode={retcode} comment={result.get('comment', '')}"
                return True, result, ""

            return False, {}, f"unsupported command_type: {command_type}"
        except Exception as e:
            return False, {}, str(e)

    @staticmethod
    def _trade_retcode_ok(retcode: int) -> bool:
        # Common MT5 success codes:
        # 10008: placed, 10009: done, 10010: done partial
        return retcode in {10008, 10009, 10010}
