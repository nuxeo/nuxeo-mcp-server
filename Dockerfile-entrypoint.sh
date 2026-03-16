#!/bin/bash
set -e

# Default values
MODE=${MCP_MODE:-http}
PORT=${MCP_PORT:-8181}
HOST=${MCP_HOST:-0.0.0.0}

# Start the server based on the mode
if [ "$MODE" = "http" ]; then
    echo "starting MCP in http mode"
    exec nuxeo-mcp --http --port "$PORT" --host "$HOST"
elif [ "$MODE" = "sse" ]; then
    echo "starting MCP in sse mode"
    exec nuxeo-mcp --sse --port "$PORT" --host "$HOST"
else
    echo "Invalid MCP_MODE: $MODE. Use either '\''http'\'' or '\''sse'\''."
    exit 1
fi
