#!/bin/bash
set -e

PORT=${MCP_PORT:-8181}
HOST=${MCP_HOST:-0.0.0.0}

# SSE was removed: fail loudly rather than serve /mcp to SSE clients.
if [ -n "${MCP_MODE:-}" ] && [ "$MCP_MODE" != "http" ]; then
    echo "MCP_MODE=$MCP_MODE is no longer supported: the image serves streamable HTTP at /mcp" >&2
    exit 1
fi

exec nuxeo-mcp --http --port "$PORT" --host "$HOST"
