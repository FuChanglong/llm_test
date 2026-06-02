#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

exec npx @modelcontextprotocol/inspector \
  --transport http \
  .venv/bin/python -m app.mcp.server
