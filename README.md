# MT5 Broker Agent

Python agent that connects to MetaTrader 5 Terminal and pushes data to Broker Service via gRPC.

## Requirements

- Python 3.10+
- MetaTrader 5 Terminal (Windows only)
- MetaTrader5 Python package

## Installation

```bash
pip install -r requirements.txt
```

## Configuration

Preferred for `mt5_agent.exe`: place `broker.cfg` in the same directory as the executable.

Example `broker.cfg`:

```ini
endpoint=localhost
port=50051
internal_token=
agentId=agent-001
agentName=MT5 Agent 1
heartbeat_interval=30
lease_seconds=60
auth_poll_interval=5
auth_wait_timeout=60
```

`config.yaml` is still supported as fallback:

```yaml
broker:
  url: "localhost:50051"
  internal_token: "your-token-here"

agent:
  id: "agent-001"
  name: "MT5 Agent 1"
  heartbeat_interval: 30  # seconds

mt5:
  login: 123456
  password: "your-password"
  server: "BrokerName-Server"
```

## Usage

```bash
python main.py
```

## Connection Test Steps

1. Start `broker_service` and confirm gRPC listen address matches `broker.cfg` (`endpoint` + `port`).
2. Set an `agentId` in `broker.cfg` that is not active in broker registry.
3. Run agent:

```bash
cd broker_agent
python main.py
```

Expected:
- Agent connects to MT5 and broker transport.
- Registration retries every `auth_poll_interval` seconds (default 5s).
- Agent exits after `auth_wait_timeout` seconds (default 60s).

4. Activate/register the same `agentId` in broker registry and rerun agent.

Expected:
- `Session registered` appears quickly.
- Heartbeat and snapshot logs continue normally.

5. (Optional) Set wrong `internal_token` in `broker.cfg` and rerun.

Expected:
- Unauthenticated/permission errors with retry loop until timeout.

## Build to .exe

```bash
pyinstaller --onefile --name mt5_agent main.py
```

## Proto Source

Protobuf definitions are sourced from `../broker_service/proto/mt5/v1/mt5.proto`
