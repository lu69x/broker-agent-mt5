from concurrent import futures
from datetime import datetime, timezone

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

    def GetPositions(self, request, context):
        self._validate_token(context)
        symbol = (request.symbol or "").strip().upper()
        positions = self.mt5.get_positions()
        if symbol:
            positions = [p for p in positions if (p.get("symbol", "").upper() == symbol)]
        return mt5_pb2.PositionsResponse(
            positions=[
                mt5_pb2.Position(
                    ticket=p.get("ticket", 0),
                    symbol=p.get("symbol", ""),
                    type=p.get("type", 0),
                    volume=p.get("volume", 0.0),
                    price_open=p.get("price_open", 0.0),
                    price_current=p.get("price_current", 0.0),
                    sl=p.get("sl", 0.0),
                    tp=p.get("tp", 0.0),
                    swap=p.get("swap", 0.0),
                    profit=p.get("profit", 0.0),
                    comment=p.get("comment", ""),
                    magic=p.get("magic", 0),
                    time=p.get("time", 0),
                    time_update=p.get("time_update", 0),
                )
                for p in positions
            ]
        )

    def GetBalances(self, request, context):
        self._validate_token(context)
        balances = self.mt5.get_balances()
        return mt5_pb2.BalancesResponse(
            balances=[
                mt5_pb2.BalanceEntry(
                    asset=b.get("asset", ""),
                    free=b.get("free", 0.0),
                    locked=b.get("locked", 0.0),
                    total=b.get("total", 0.0),
                )
                for b in balances
            ]
        )

    def GetSymbolInfo(self, request, context):
        self._validate_token(context)
        symbol = (request.symbol or "").strip().upper()
        if not symbol:
            context.abort(grpc.StatusCode.INVALID_ARGUMENT, "symbol is required")
        info = self.mt5.get_symbol_info(symbol)
        if not info:
            context.abort(grpc.StatusCode.UNAVAILABLE, f"symbol info is not available for {symbol}")
        return mt5_pb2.SymbolInfoResponse(
            symbol=mt5_pb2.SymbolInfo(
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
        )

    def GetRatesRange(self, request, context):
        self._validate_token(context)
        symbol = (request.symbol or "").strip().upper()
        timeframe = (request.timeframe or "").strip().upper()
        if not symbol:
            context.abort(grpc.StatusCode.INVALID_ARGUMENT, "symbol is required")
        if not timeframe:
            context.abort(grpc.StatusCode.INVALID_ARGUMENT, "timeframe is required")

        from_ts = int(getattr(request, "from", 0) or 0)
        to_ts = int(getattr(request, "to", 0) or 0)
        count = 100
        if from_ts > 0 and to_ts > 0 and to_ts > from_ts:
            approx = max(1, int((to_ts - from_ts) / 60))
            count = min(5000, approx)
        rates = self.mt5.get_rates(symbol, timeframe, count=count)
        return mt5_pb2.RatesResponse(
            symbol=symbol,
            timeframe=timeframe,
            values=[
                mt5_pb2.Rate(
                    time=r.get("time", 0),
                    open=r.get("open", 0.0),
                    high=r.get("high", 0.0),
                    low=r.get("low", 0.0),
                    close=r.get("close", 0.0),
                    tick_volume=r.get("tick_volume", 0),
                    spread=r.get("spread", 0),
                    real_volume=r.get("real_volume", 0),
                )
                for r in rates
            ],
        )

    def GetOpenOrders(self, request, context):
        self._validate_token(context)
        symbol = (request.symbol or "").strip().upper()
        orders = self.mt5.get_orders()
        if symbol:
            orders = [o for o in orders if (o.get("symbol", "").upper() == symbol)]
        return mt5_pb2.OpenOrdersResponse(
            orders=[
                mt5_pb2.TradeOrder(
                    ticket=o.get("ticket", 0),
                    symbol=o.get("symbol", ""),
                    type=o.get("type", 0),
                    state=o.get("state", 0),
                    volume_initial=o.get("volume_initial", 0.0),
                    volume_current=o.get("volume_current", 0.0),
                    price_open=o.get("price_open", 0.0),
                    sl=o.get("sl", 0.0),
                    tp=o.get("tp", 0.0),
                    magic=o.get("magic", 0),
                    comment=o.get("comment", ""),
                    time_setup=o.get("time_setup", 0),
                    time_done=o.get("time_done", 0),
                )
                for o in orders
            ]
        )

    def GetHistoryOrders(self, request, context):
        self._validate_token(context)
        symbol = (request.symbol or "").strip().upper()
        req_from = int(getattr(request, "from", 0) or 0)
        from_dt = datetime.fromtimestamp(req_from, tz=timezone.utc) if req_from else None
        to_dt = datetime.fromtimestamp(request.to or 0, tz=timezone.utc) if request.to else None
        orders = self.mt5.get_history_orders(symbol=symbol, from_date=from_dt, to_date=to_dt)
        return mt5_pb2.HistoryOrdersResponse(
            orders=[
                mt5_pb2.TradeOrder(
                    ticket=o.get("ticket", 0),
                    symbol=o.get("symbol", ""),
                    type=o.get("type", 0),
                    state=o.get("state", 0),
                    volume_initial=o.get("volume_initial", 0.0),
                    volume_current=o.get("volume_current", 0.0),
                    price_open=o.get("price_open", 0.0),
                    sl=o.get("sl", 0.0),
                    tp=o.get("tp", 0.0),
                    magic=o.get("magic", 0),
                    comment=o.get("comment", ""),
                    time_setup=o.get("time_setup", 0),
                    time_done=o.get("time_done", 0),
                )
                for o in orders
            ]
        )

    def OrderSend(self, request, context):
        self._validate_token(context)
        payload = {
            "action": request.action,
            "symbol": request.symbol,
            "volume": request.volume,
            "type": request.type,
            "price": request.price,
            "sl": request.sl,
            "tp": request.tp,
            "order": request.order,
        }
        result = self.mt5.order_send(payload)
        if not result:
            context.abort(grpc.StatusCode.UNAVAILABLE, "mt5 order_send failed")
        return mt5_pb2.OrderSendResponse(
            retcode=result.get("retcode", 0),
            deal=result.get("deal", 0),
            order=result.get("order", 0),
            volume=result.get("volume", 0.0),
            price=result.get("price", 0.0),
            bid=result.get("bid", 0.0),
            ask=result.get("ask", 0.0),
            comment=result.get("comment", ""),
            request_id=result.get("request_id", 0),
            retcode_external=result.get("retcode_external", 0),
        )

    def OrderCancel(self, request, context):
        self._validate_token(context)
        payload = {
            "order": request.order,
            "symbol": request.symbol,
        }
        result = self.mt5.order_cancel(payload)
        if not result:
            context.abort(grpc.StatusCode.UNAVAILABLE, "mt5 order_cancel failed")
        return mt5_pb2.OrderCancelResponse(
            retcode=result.get("retcode", 0),
            order=result.get("order", request.order),
            comment=result.get("comment", ""),
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
