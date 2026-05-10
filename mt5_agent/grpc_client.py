"""gRPC Client for Broker Service.

Communicates with MT5IngressService on the broker.
"""
import sys
from pathlib import Path
from typing import Optional

import grpc
from google.protobuf import empty_pb2

from .logger import get_logger

logger = get_logger(__name__)

def _load_proto_modules():
    """Load generated proto modules with fallbacks for packaged Windows builds."""
    try:
        from proto.mt5.v1 import mt5_pb2 as _mt5_pb2, mt5_pb2_grpc as _mt5_pb2_grpc
        return _mt5_pb2, _mt5_pb2_grpc
    except ImportError:
        pass

    # Fallback for generated stubs that use `import mt5_pb2` (top-level import).
    # Ensure proto/mt5/v1 is on sys.path so mt5_pb2_grpc can resolve mt5_pb2.
    candidates = [
        Path(__file__).resolve().parent.parent / "proto" / "mt5" / "v1",
        Path(getattr(sys, "_MEIPASS", "")) / "proto" / "mt5" / "v1",
    ]
    for candidate in candidates:
        if candidate.exists():
            candidate_str = str(candidate)
            if candidate_str not in sys.path:
                sys.path.insert(0, candidate_str)
            try:
                import mt5_pb2 as _mt5_pb2
                import mt5_pb2_grpc as _mt5_pb2_grpc
                return _mt5_pb2, _mt5_pb2_grpc
            except ImportError:
                continue

    return None, None


mt5_pb2, mt5_pb2_grpc = _load_proto_modules()
if mt5_pb2 is None or mt5_pb2_grpc is None:
    logger.warning("Proto files not generated/importable yet. Run: bash generate_proto.sh")


class BrokerClient:
    """gRPC client for Broker Service MT5IngressService."""

    def __init__(self, config: dict):
        self.config = config.get("broker", {})
        self.url = self.config.get("url", "localhost:50051")
        self.token = self.config.get("internal_token", "")
        self.channel: Optional[grpc.Channel] = None
        self.stub = None

    def connect(self) -> bool:
        """Connect to broker service."""
        if mt5_pb2 is None:
            logger.error("Proto files not generated/importable. Run: bash generate_proto.sh")
            return False

        try:
            self.channel = grpc.insecure_channel(self.url)
            grpc.channel_ready_future(self.channel).result(timeout=5)
            self.stub = mt5_pb2_grpc.MT5IngressServiceStub(self.channel)
            logger.info(f"Connected to broker at {self.url}")
            return True
        except Exception as e:
            logger.error(f"Failed to connect to broker: {e}")
            return False

    def disconnect(self):
        """Disconnect from broker service."""
        if self.channel:
            self.channel.close()
            self.channel = None
            self.stub = None
            logger.info("Disconnected from broker")

    def _metadata(self) -> list[tuple[str, str]]:
        """Create request metadata with auth token."""
        if self.token:
            return [("x-internal-token", self.token)]
        return []

    def register_session(self, agent_id: str, agent_name: str, lease_seconds: int = 60) -> dict:
        """Register agent session."""
        if not self.stub:
            return {"success": False, "error": "Not connected"}

        try:
            request = mt5_pb2.RegisterSessionRequest(
                agent_id=agent_id,
                agent_name=agent_name,
                lease_seconds=lease_seconds,
            )
            response = self.stub.RegisterSession(request, metadata=self._metadata())
            return {
                "success": True,
                "state": response.state,
                "agent_id": response.agent_id,
                "agent_name": response.agent_name,
                "last_error": response.last_error,
            }
        except grpc.RpcError as e:
            logger.error(f"RegisterSession failed: {e.code()} - {e.details()}")
            return {
                "success": False,
                "error": str(e),
                "code": str(e.code()),
                "details": e.details(),
            }
        except Exception as e:
            logger.error(f"RegisterSession error: {e}")
            return {"success": False, "error": str(e)}

    def heartbeat(self, agent_id: str, lease_seconds: int = 60) -> dict:
        """Send heartbeat to refresh lease."""
        if not self.stub:
            return {"success": False, "error": "Not connected"}

        try:
            request = mt5_pb2.HeartbeatRequest(
                agent_id=agent_id,
                lease_seconds=lease_seconds,
            )
            response = self.stub.Heartbeat(request, metadata=self._metadata())
            return {
                "success": True,
                "state": response.state,
                "last_error": response.last_error,
            }
        except grpc.RpcError as e:
            logger.error(f"Heartbeat failed: {e.code()} - {e.details()}")
            return {"success": False, "error": str(e)}
        except Exception as e:
            logger.error(f"Heartbeat error: {e}")
            return {"success": False, "error": str(e)}

    def publish_snapshot(self, snapshot: dict) -> dict:
        """Publish MT5 data snapshot."""
        if not self.stub:
            return {"success": False, "error": "Not connected"}

        try:
            request = self._build_snapshot_request(snapshot)
            response = self.stub.PublishSnapshot(request, metadata=self._metadata())
            return {
                "success": True,
                "state": response.state,
                "last_error": response.last_error,
            }
        except grpc.RpcError as e:
            logger.error(f"PublishSnapshot failed: {e.code()} - {e.details()}")
            return {"success": False, "error": str(e)}
        except Exception as e:
            logger.error(f"PublishSnapshot error: {e}")
            return {"success": False, "error": str(e)}

    def get_status(self) -> dict:
        """Get connection status."""
        if not self.stub:
            return {"success": False, "error": "Not connected"}

        try:
            response = self.stub.GetStatus(empty_pb2.Empty(), metadata=self._metadata())
            return {
                "success": True,
                "state": response.state,
                "agent_id": response.agent_id,
                "agent_name": response.agent_name,
                "last_error": response.last_error,
            }
        except grpc.RpcError as e:
            logger.error(f"GetStatus failed: {e.code()} - {e.details()}")
            return {
                "success": False,
                "error": str(e),
                "code": str(e.code()),
                "details": e.details(),
            }
        except Exception as e:
            logger.error(f"GetStatus error: {e}")
            return {"success": False, "error": str(e)}

    def _build_snapshot_request(self, snapshot: dict) -> "mt5_pb2.PublishSnapshotRequest":
        """Build PublishSnapshotRequest from dict."""
        request = mt5_pb2.PublishSnapshotRequest(agent_id=snapshot["agent_id"])

        # Account info
        if account := snapshot.get("account"):
            request.account.CopyFrom(self._build_account(account))

        # Positions
        for pos in snapshot.get("positions", []):
            request.positions.append(self._build_position(pos))

        # Balances
        for bal in snapshot.get("balances", []):
            request.balances.append(self._build_balance(bal))

        # Open orders
        for order in snapshot.get("open_orders", []):
            request.open_orders.append(self._build_order(order))

        # History orders
        for order in snapshot.get("history_orders", []):
            request.history_orders.append(self._build_order(order))

        # Ticks
        for tick_envelope in snapshot.get("ticks", []):
            env = mt5_pb2.SymbolTickEnvelope(symbol=tick_envelope["symbol"])
            env.tick.CopyFrom(self._build_tick(tick_envelope["tick"]))
            request.ticks.append(env)

        # Rates
        for rates_envelope in snapshot.get("rates", []):
            env = mt5_pb2.RatesEnvelope(
                symbol=rates_envelope["symbol"],
                timeframe=rates_envelope["timeframe"],
            )
            for rate in rates_envelope["values"]:
                env.values.append(self._build_rate(rate))
            request.rates.append(env)

        # Symbol infos
        for info in snapshot.get("symbol_infos", []):
            request.symbol_infos.append(self._build_symbol_info(info))

        return request

    def _build_account(self, acc: dict) -> "mt5_pb2.AccountInfo":
        return mt5_pb2.AccountInfo(
            login=acc.get("login", 0),
            leverage=acc.get("leverage", 0),
            balance=acc.get("balance", 0.0),
            equity=acc.get("equity", 0.0),
            margin=acc.get("margin", 0.0),
            margin_free=acc.get("margin_free", 0.0),
            margin_level=acc.get("margin_level", 0.0),
            profit=acc.get("profit", 0.0),
            currency=acc.get("currency", ""),
            server=acc.get("server", ""),
            company=acc.get("company", ""),
            trade_allowed=acc.get("trade_allowed", False),
            trade_expert=acc.get("trade_expert", False),
            limit_orders=acc.get("limit_orders", 0),
            margin_so_call=acc.get("margin_so_call", 0.0),
            margin_so_so=acc.get("margin_so_so", 0.0),
            currency_digits=acc.get("currency_digits", 0),
        )

    def _build_position(self, pos: dict) -> "mt5_pb2.Position":
        return mt5_pb2.Position(
            ticket=pos.get("ticket", 0),
            symbol=pos.get("symbol", ""),
            type=pos.get("type", 0),
            volume=pos.get("volume", 0.0),
            price_open=pos.get("price_open", 0.0),
            price_current=pos.get("price_current", 0.0),
            sl=pos.get("sl", 0.0),
            tp=pos.get("tp", 0.0),
            swap=pos.get("swap", 0.0),
            profit=pos.get("profit", 0.0),
            comment=pos.get("comment", ""),
            magic=pos.get("magic", 0),
            time=pos.get("time", 0),
            time_update=pos.get("time_update", 0),
        )

    def _build_balance(self, bal: dict) -> "mt5_pb2.BalanceEntry":
        return mt5_pb2.BalanceEntry(
            asset=bal.get("asset", ""),
            free=bal.get("free", 0.0),
            locked=bal.get("locked", 0.0),
            total=bal.get("total", 0.0),
        )

    def _build_order(self, order: dict) -> "mt5_pb2.TradeOrder":
        return mt5_pb2.TradeOrder(
            ticket=order.get("ticket", 0),
            symbol=order.get("symbol", ""),
            type=order.get("type", 0),
            state=order.get("state", 0),
            volume_initial=order.get("volume_initial", 0.0),
            volume_current=order.get("volume_current", 0.0),
            price_open=order.get("price_open", 0.0),
            sl=order.get("sl", 0.0),
            tp=order.get("tp", 0.0),
            magic=order.get("magic", 0),
            comment=order.get("comment", ""),
            time_setup=order.get("time_setup", 0),
            time_done=order.get("time_done", 0),
        )

    def _build_tick(self, tick: dict) -> "mt5_pb2.SymbolTick":
        return mt5_pb2.SymbolTick(
            time=tick.get("time", 0),
            bid=tick.get("bid", 0.0),
            ask=tick.get("ask", 0.0),
            last=tick.get("last", 0.0),
            volume=tick.get("volume", 0),
            time_msc=tick.get("time_msc", 0),
            flags=tick.get("flags", 0),
            volume_real=tick.get("volume_real", 0.0),
        )

    def _build_rate(self, rate: dict) -> "mt5_pb2.Rate":
        return mt5_pb2.Rate(
            time=rate.get("time", 0),
            open=rate.get("open", 0.0),
            high=rate.get("high", 0.0),
            low=rate.get("low", 0.0),
            close=rate.get("close", 0.0),
            tick_volume=rate.get("tick_volume", 0),
            spread=rate.get("spread", 0),
            real_volume=rate.get("real_volume", 0),
        )

    def _build_symbol_info(self, info: dict) -> "mt5_pb2.SymbolInfo":
        return mt5_pb2.SymbolInfo(
            symbol=info.get("symbol", ""),
            description=info.get("description", ""),
            currency_base=info.get("currency_base", ""),
            currency_profit=info.get("currency_profit", ""),
            digits=info.get("digits", 0),
            point=info.get("point", 0.0),
            volume_min=info.get("volume_min", 0.0),
            volume_max=info.get("volume_max", 0.0),
            volume_step=info.get("volume_step", 0.0),
            visible=info.get("visible", False),
        )
