#!/usr/bin/env python3
"""
MT5 Broker Agent - Main Entry Point

Connects to MetaTrader 5 Terminal and pushes data to Broker Service via gRPC.
"""
import asyncio
import configparser
import signal
import sys
from pathlib import Path

import yaml

from mt5_agent.agent import MT5Agent
from mt5_agent.logger import get_logger

logger = get_logger(__name__)


def load_config(config_path: str = "config.yaml") -> dict:
    """Load configuration from YAML file."""
    base_dir = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent
    cfg_path = base_dir / "broker.cfg"
    if cfg_path.exists():
        return load_cfg_file(cfg_path)

    path = Path(config_path)
    if not path.exists():
        # Try local config
        local_path = Path("config.local.yaml")
        if local_path.exists():
            path = local_path
        else:
            raise FileNotFoundError(f"Config file not found: {config_path}")

    with open(path, "r") as f:
        return yaml.safe_load(f)


def load_cfg_file(cfg_path: Path) -> dict:
    """Load configuration from broker.cfg in same directory as executable."""
    parser = configparser.ConfigParser()
    raw_text = cfg_path.read_text(encoding="utf-8")

    # Support key=value files without sections.
    if "[" not in raw_text:
        raw_text = "[broker]\n" + raw_text

    parser.read_string(raw_text)

    broker_section = parser["broker"] if "broker" in parser else {}
    agent_section = parser["agent"] if "agent" in parser else broker_section
    mt5_section = parser["mt5"] if "mt5" in parser else {}

    endpoint = broker_section.get("endpoint", "").strip()
    port = broker_section.get("port", "").strip()
    url = broker_section.get("url", "").strip()
    broker_url = url or f"{endpoint}:{port}".strip(":") or "localhost:50051"

    return {
        "broker": {
            "url": broker_url,
            "internal_token": broker_section.get("internal_token", ""),
        },
        "agent": {
            "id": agent_section.get("agentId", agent_section.get("id", "agent-001")),
            "name": agent_section.get("agentName", agent_section.get("name", "MT5 Agent")),
            "heartbeat_interval": int(agent_section.get("heartbeat_interval", "30")),
            "lease_seconds": int(agent_section.get("lease_seconds", "60")),
            "auth_poll_interval": int(agent_section.get("auth_poll_interval", "5")),
            "auth_wait_timeout": int(agent_section.get("auth_wait_timeout", "60")),
        },
        "mt5": {
            "login": int(mt5_section.get("login", "0")),
            "password": mt5_section.get("password", ""),
            "server": mt5_section.get("server", ""),
            "timeout": int(mt5_section.get("timeout", "60000")),
        },
        "collection": {
            "interval": int(parser.get("collection", "interval", fallback="5")),
            "symbols": [s.strip() for s in parser.get("collection", "symbols", fallback="EURUSD").split(",") if s.strip()],
            "timeframes": [s.strip() for s in parser.get("collection", "timeframes", fallback="M1").split(",") if s.strip()],
        },
    }


async def main():
    """Main entry point."""
    logger.info("MT5 Broker Agent starting...")

    # Load configuration
    config = load_config()
    logger.info(f"Agent ID: {config['agent']['id']}")
    logger.info(f"Broker URL: {config['broker']['url']}")

    # Create agent
    agent = MT5Agent(config)

    # Setup signal handlers
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, lambda: asyncio.create_task(agent.stop()))

    # Start agent
    try:
        await agent.start()
        await agent.run()  # Run until stopped
    except Exception as e:
        logger.error(f"Agent error: {e}", exc_info=True)
        return 1
    finally:
        await agent.stop()

    logger.info("MT5 Broker Agent stopped")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
