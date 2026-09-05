#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
PLATFORM="$ROOT/platform"
PY="$PLATFORM/.venv/bin/python"
exec "$PY" "$PLATFORM/daemon.py" status "$@"
