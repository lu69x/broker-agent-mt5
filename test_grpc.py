#!/usr/bin/env python3
"""Test gRPC connection to broker service."""
import configparser
from mt5_agent.grpc_client import BrokerClient

def test_connection():
    # Load config
    config = configparser.ConfigParser()
    config.read("broker.cfg")

    # Create broker client
    # Note: grpc_client expects 'url' but cfg has 'endpoint' + 'port'
    broker_cfg = config["broker"]
    broker_url = f"{broker_cfg.get('endpoint', 'localhost')}:{broker_cfg.get('port', '50051')}"

    client_config = {
        "broker": {
            "url": broker_url,
            "internal_token": broker_cfg.get("internal_token", "")
        }
    }

    client = BrokerClient(client_config)

    print(f"Testing connection to broker at: {broker_url}")

    # Test connection
    if client.connect():
        print("✓ Connected to broker!")

        # Test GetStatus
        print("\nTesting GetStatus...")
        status = client.get_status()
        print(f"GetStatus response: {status}")

        # Test Reverse Stream Connect
        print("\nTesting Connect stream...")
        agent_cfg = config["agent"]
        result = client.start_reverse_stream(
            agent_id=agent_cfg["agentId"],
            agent_name=agent_cfg["agentName"],
            lease_seconds=agent_cfg.getint("lease_seconds", 60),
            startup_timeout=10,
            command_handler=lambda _cmd, _payload: (False, {}, "test mode"),
        )
        print(f"Connect response: {result}")
        if result.get("success"):
            client.send_heartbeat(lease_seconds=agent_cfg.getint("lease_seconds", 60))

        client.disconnect()
        print("\n✓ Test completed!")
    else:
        print("✗ Failed to connect to broker")
        print("  Make sure broker service is running on", broker_url)

if __name__ == "__main__":
    test_connection()
