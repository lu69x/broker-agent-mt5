"""MT5 Broker Agent - Main Agent Class

Orchestrates MT5 connection, data collection, and gRPC communication.
"""
import asyncio
import time

from .mt5_connector import MT5Connector
from .grpc_client import BrokerClient
from .pull_server import PullRPCServer
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
        self.collection_interval = self.collection_config.get("interval", 5)
        self.auth_poll_interval = self.agent_config.get("auth_poll_interval", 5)
        self.auth_wait_timeout = self.agent_config.get("auth_wait_timeout", 60)

        self.mt5 = MT5Connector(config)
        self.broker = BrokerClient(config)
        self.pull_host = self.agent_config.get("grpc_host", "0.0.0.0")
        self.pull_port = int(self.agent_config.get("grpc_port", 50051))
        self.pull_server = PullRPCServer(self.mt5, self.pull_host, self.pull_port, self.config.get("broker", {}).get("internal_token", ""))

        self._running = False
        self._tasks = []

    async def start(self):
        """Start the agent."""
        logger.info("Starting MT5 Agent...")

        # Connect to MT5
        if not self.mt5.connect():
            logger.error("Failed to connect to MT5 Terminal")
            raise RuntimeError("MT5 connection failed")

        # Connect to broker
        if not self.broker.connect():
            logger.error("Failed to connect to Broker Service")
            self.mt5.disconnect()
            raise RuntimeError("Broker connection failed")

        # Register session (wait for authorization if needed)
        result = await self._register_with_authorization_wait()
        if not result.get("success"):
            self.broker.disconnect()
            self.mt5.disconnect()
            raise RuntimeError("Session registration failed")

        logger.info(f"Session registered: {result.get('state')}")
        self.pull_server.start()

        self._running = True

        # Start background tasks
        self._tasks = [
            asyncio.create_task(self._heartbeat_loop()),
        ]

    async def stop(self):
        """Stop the agent."""
        if not self._running:
            return

        logger.info("Stopping MT5 Agent...")
        self._running = False

        # Cancel tasks
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)

        # Disconnect
        self.pull_server.stop()
        self.broker.disconnect()
        self.mt5.disconnect()

    async def run(self):
        """Run agent until stopped."""
        while self._running:
            await asyncio.sleep(1)

    async def _heartbeat_loop(self):
        """Send periodic heartbeats."""
        while self._running:
            try:
                result = self.broker.heartbeat(
                    agent_id=self.agent_id,
                    lease_seconds=self.lease_seconds,
                )
                if result.get("success"):
                    logger.debug(f"Heartbeat: {result.get('state')}")
                else:
                    logger.warning(f"Heartbeat failed: {result.get('error')}")
            except Exception as e:
                logger.error(f"Heartbeat error: {e}")

            await asyncio.sleep(self.heartbeat_interval)

    async def _register_with_authorization_wait(self) -> dict:
        """Attempt registration and poll while waiting for broker authorization."""
        deadline = time.monotonic() + self.auth_wait_timeout
        attempts = 0
        last_error = "unknown error"

        while True:
            attempts += 1
            result = self.broker.register_session(
                agent_id=self.agent_id,
                agent_name=self.agent_name,
                lease_seconds=self.lease_seconds,
                host=self.pull_host,
                port=str(self.pull_port),
            )

            if result.get("success"):
                logger.info(f"Session registered: {result.get('state')}")
                return result

            last_error = result.get("details") or result.get("error", "registration failed")
            if not self._should_wait_for_authorization(result):
                logger.error(f"Failed to register session: {last_error}")
                return result

            if time.monotonic() >= deadline:
                logger.error(
                    "Agent is not authorized after %ss. Last error: %s",
                    self.auth_wait_timeout,
                    last_error,
                )
                return {"success": False, "error": last_error}

            logger.warning(
                "Agent not authorized yet (attempt %s). Retrying in %ss...",
                attempts,
                self.auth_poll_interval,
            )
            await asyncio.sleep(self.auth_poll_interval)

    @staticmethod
    def _should_wait_for_authorization(result: dict) -> bool:
        code = (result.get("code") or "").upper()
        details = (result.get("details") or result.get("error") or "").lower()
        if "not registered or not active" in details:
            return True
        return code in {
            "STATUS_CODE.UNAUTHENTICATED",
            "STATUS_CODE.PERMISSION_DENIED",
        }
