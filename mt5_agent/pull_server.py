from concurrent import futures

import grpc

from .grpc_client import mt5_pb2, mt5_pb2_grpc
from .logger import get_logger

logger = get_logger(__name__)


class MT5BrokerService(mt5_pb2_grpc.MT5BrokerServiceServicer):
    def __init__(self, mt5_connector, token: str):
        self.mt5 = mt5_connector
        self.token = token or ""

    def _validate_token(self, context) -> bool:
        if not self.token:
            return True
        md = dict(context.invocation_metadata())
        if md.get("x-internal-token", "") != self.token:
            context.abort(grpc.StatusCode.UNAUTHENTICATED, "invalid internal token")
            return False
        return True

    def GetAccountInfo(self, request, context):
        self._validate_token(context)
        account = self.mt5.get_account()
        if not account:
            context.abort(grpc.StatusCode.UNAVAILABLE, "mt5 account is not available")

        return mt5_pb2.AccountInfoResponse(
            account=mt5_pb2.AccountInfo(
                login=account.get("login", 0),
                leverage=account.get("leverage", 0),
                balance=account.get("balance", 0.0),
                equity=account.get("equity", 0.0),
                margin=account.get("margin", 0.0),
                margin_free=account.get("margin_free", 0.0),
                margin_level=account.get("margin_level", 0.0),
                profit=account.get("profit", 0.0),
                currency=account.get("currency", ""),
                server=account.get("server", ""),
                company=account.get("company", ""),
                trade_allowed=account.get("trade_allowed", False),
                trade_expert=account.get("trade_expert", False),
                limit_orders=account.get("limit_orders", 0),
                margin_so_call=account.get("margin_so_call", 0.0),
                margin_so_so=account.get("margin_so_so", 0.0),
                currency_digits=account.get("currency_digits", 0),
            )
        )

    def GetSymbolTick(self, request, context):
        self._validate_token(context)
        symbol = request.symbol
        if not symbol:
            context.abort(grpc.StatusCode.INVALID_ARGUMENT, "symbol is required")

        tick = self.mt5.get_symbol_tick(symbol)
        if not tick:
            context.abort(grpc.StatusCode.UNAVAILABLE, f"symbol tick is not available for {symbol}")

        return mt5_pb2.SymbolTickResponse(
            symbol=symbol,
            tick=mt5_pb2.SymbolTick(
                time=tick.get("time", 0),
                bid=tick.get("bid", 0.0),
                ask=tick.get("ask", 0.0),
                last=tick.get("last", 0.0),
                volume=tick.get("volume", 0.0),
                time_msc=tick.get("time_msc", 0),
                flags=tick.get("flags", 0),
                volume_real=tick.get("volume_real", 0.0),
            ),
        )


class PullRPCServer:
    def __init__(self, mt5_connector, host: str, port: int, token: str):
        self.host = host
        self.port = int(port)
        self.server = grpc.server(futures.ThreadPoolExecutor(max_workers=4))
        mt5_pb2_grpc.add_MT5BrokerServiceServicer_to_server(MT5BrokerService(mt5_connector, token), self.server)
        self.server.add_insecure_port(f"{self.host}:{self.port}")

    def start(self):
        self.server.start()
        logger.info("MT5 pull gRPC server started on %s:%s", self.host, self.port)

    def stop(self):
        self.server.stop(grace=2)
        logger.info("MT5 pull gRPC server stopped")
