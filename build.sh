#!/bin/bash
# Build MT5 Agent to .exe using PyInstaller

set -euo pipefail

echo "Building MT5 Agent..."

# Generate proto stubs first
bash generate_proto.sh

# PyInstaller add-data separator differs by platform:
# - Windows: ';'
# - POSIX: ':'
if [[ "${OS:-}" == "Windows_NT" ]] || [[ "$(uname -s)" =~ MINGW|MSYS|CYGWIN ]]; then
  ADD_DATA_SEP=";"
else
  ADD_DATA_SEP=":"
fi

# Build with PyInstaller
pyinstaller \
  --noconfirm \
  --clean \
  --onefile \
  --name mt5_agent \
  --add-data "config.yaml${ADD_DATA_SEP}." \
  --collect-submodules proto \
  --hidden-import MetaTrader5 \
  --hidden-import numpy \
  --hidden-import grpc \
  --hidden-import google.protobuf \
  main.py

echo "Build complete! Executable: dist/mt5_agent.exe"
