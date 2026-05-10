#!/bin/bash
# Build MT5 Agent to .exe using PyInstaller

echo "Building MT5 Agent..."

# Generate proto stubs first
bash generate_proto.sh

# Build with PyInstaller
pyinstaller \
  --onefile \
  --name mt5_agent \
  --add-data "config.yaml:." \
  --hidden-import MetaTrader5 \
  --hidden-import grpc \
  --hidden-import protobuf \
  main.py

echo "Build complete! Executable: dist/mt5_agent.exe"
