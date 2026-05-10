#!/bin/bash
# Generate Python gRPC stubs from mt5.proto

PROTO_DIR="../broker_service/proto/mt5/v1"
OUTPUT_DIR="proto/mt5/v1"

mkdir -p "$OUTPUT_DIR"

python -m grpc_tools.protoc \
  --proto_path="$PROTO_DIR" \
  --python_out="$OUTPUT_DIR" \
  --grpc_python_out="$OUTPUT_DIR" \
  "$PROTO_DIR/mt5.proto"

echo "Generated gRPC stubs in $OUTPUT_DIR"
