#!/bin/bash
# Generate Python gRPC stubs from mt5.proto

PROTO_DIR="../broker_service/proto/mt5/v1"
OUTPUT_DIR="proto/mt5/v1"

mkdir -p "$OUTPUT_DIR"
mkdir -p "proto" "proto/mt5"
touch "proto/__init__.py" "proto/mt5/__init__.py" "$OUTPUT_DIR/__init__.py"

PYTHONWARNINGS="ignore:pkg_resources is deprecated as an API:UserWarning" \
python -m grpc_tools.protoc \
  --proto_path="$PROTO_DIR" \
  --python_out="$OUTPUT_DIR" \
  --grpc_python_out="$OUTPUT_DIR" \
  "$PROTO_DIR/mt5.proto"

# grpc_tools may emit `import mt5_pb2 as ...` in mt5_pb2_grpc.py which can break
# package imports (e.g. `from proto.mt5.v1 import mt5_pb2_grpc`) in frozen builds.
if [ -f "$OUTPUT_DIR/mt5_pb2_grpc.py" ]; then
  sed -i.bak 's/^import mt5_pb2 as mt5__pb2$/from . import mt5_pb2 as mt5__pb2/' "$OUTPUT_DIR/mt5_pb2_grpc.py"
  rm -f "$OUTPUT_DIR/mt5_pb2_grpc.py.bak"
fi

echo "Generated gRPC stubs in $OUTPUT_DIR"
