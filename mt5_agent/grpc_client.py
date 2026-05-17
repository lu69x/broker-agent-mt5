"""gRPC Client for Broker Service.

Reverse-stream client for MT5IngressService.Connect.
"""
import queue
import sys
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Optional

import grpc
from google.protobuf import empty_pb2
from google.protobuf.json_format import MessageToDict
from google.protobuf.struct_pb2 import Struct

from .logger import get_logger

logger = get_logger(__name__)



def _load_proto_modules():
    """Load generated proto modules with fallbacks for packaged Windows builds."""
    try:
        from proto.mt5.v1 import mt5_pb2 as _mt5_pb2, mt5_pb2_grpc as _mt5_pb2_grpc
        return _mt5_pb2, _mt5_pb2_grpc
    except ImportError:
        pass

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

        self._stream_thread: Optional[threading.Thread] = None
        self._stream_running = False
        self._ready_event = threading.Event()
        self._last_error = ""
        self._outgoing: "queue.Queue[Optional[Any]]" = queue.Queue()

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
        self.stop_stream()
        if self.channel:
            self.channel.close()
            self.channel = None
            self.stub = None
            logger.info("Disconnected from broker")

    def _metadata(self) -> list[tuple[str, str]]:
        if self.token:
            return [("x-internal-token", self.token)]
        return []

    def start_reverse_stream(
        self,
        agent_id: str,
        agent_name: str,
        lease_seconds: int,
        startup_timeout: int,
        command_handler: Callable[[str, dict], tuple[bool, dict, str]],
    ) -> dict:
        """Open reverse stream and wait for broker ack."""
        if not self.stub:
            return {"success": False, "error": "Not connected"}

        self._ready_event.clear()
        self._last_error = ""
        self._stream_running = True

        self._outgoing.put(
            mt5_pb2.AgentMessage(
                hello=mt5_pb2.AgentHello(
                    agent_id=agent_id,
                    agent_name=agent_name,
                    lease_seconds=lease_seconds,
                    agent_version="1.0.0",
                )
            )
        )

        self._stream_thread = threading.Thread(
            target=self._stream_loop,
            args=(command_handler,),
            daemon=True,
        )
        self._stream_thread.start()

        if not self._ready_event.wait(timeout=max(1, startup_timeout)):
            self.stop_stream()
            err = self._last_error or "reverse stream startup timeout"
            return {"success": False, "error": err}

        return {"success": True, "state": "connected"}

    def stop_stream(self):
        if not self._stream_running:
            return
        self._stream_running = False
        self._outgoing.put(None)
        if self._stream_thread and self._stream_thread.is_alive():
            self._stream_thread.join(timeout=2)
        self._stream_thread = None

    def stream_alive(self) -> bool:
        return self._stream_running and self._stream_thread is not None and self._stream_thread.is_alive()

    def send_heartbeat(self, lease_seconds: int = 60):
        if not self.stream_alive():
            return
        self._outgoing.put(
            mt5_pb2.AgentMessage(
                heartbeat=mt5_pb2.AgentHeartbeat(
                    lease_seconds=lease_seconds,
                )
            )
        )

    def publish_event(self, event_id: str, event_type: str, payload: dict):
        if not self.stream_alive():
            return
        struct_payload = Struct()
        struct_payload.update(payload or {})
        self._outgoing.put(
            mt5_pb2.AgentMessage(
                event=mt5_pb2.AgentEvent(
                    event_id=event_id,
                    event_type=event_type,
                    payload=struct_payload,
                )
            )
        )

    def get_last_error(self) -> str:
        return self._last_error

    def _request_iter(self):
        while self._stream_running:
            item = self._outgoing.get()
            if item is None:
                return
            yield item

    def _stream_loop(self, command_handler: Callable[[str, dict], tuple[bool, dict, str]]):
        try:
            stream = self.stub.Connect(self._request_iter(), metadata=self._metadata())
            for incoming in stream:
                body = incoming.WhichOneof("body")
                if body == "ack":
                    self._ready_event.set()
                    logger.info("Broker stream acknowledged")
                    continue
                if body != "command":
                    continue

                command = incoming.command
                payload = MessageToDict(command.payload, preserving_proto_field_name=True) if command.payload else {}

                try:
                    success, result_payload, err_msg = command_handler(command.command_type, payload)
                except Exception as e:
                    success, result_payload, err_msg = False, {}, str(e)

                out_struct = Struct()
                out_struct.update(self._proto_compatible(result_payload or {}))
                self._outgoing.put(
                    mt5_pb2.AgentMessage(
                        result=mt5_pb2.AgentCommandResult(
                            command_id=command.command_id,
                            success=bool(success),
                            payload=out_struct,
                            error=err_msg or "",
                        )
                    )
                )
        except grpc.RpcError as e:
            self._last_error = f"{e.code()}: {e.details()}"
            logger.error(f"Reverse stream failed: {self._last_error}")
        except Exception as e:
            self._last_error = str(e)
            logger.error(f"Reverse stream error: {e}")
        finally:
            self._stream_running = False
            self._ready_event.set()

    def _proto_compatible(self, value: Any) -> Any:
        """Normalize payload into protobuf Struct-compatible primitives."""
        if value is None:
            return None
        if isinstance(value, (str, bool, int, float)):
            return value
        if isinstance(value, datetime):
            return value.isoformat()
        if isinstance(value, dict):
            return {str(k): self._proto_compatible(v) for k, v in value.items()}
        if isinstance(value, (list, tuple)):
            return [self._proto_compatible(v) for v in value]

        # Handle numpy / scalar-like values.
        item = getattr(value, "item", None)
        if callable(item):
            try:
                return self._proto_compatible(item())
            except Exception:
                pass

        # Last-resort fallback keeps stream alive instead of crashing.
        return str(value)

    def get_status(self) -> dict:
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
