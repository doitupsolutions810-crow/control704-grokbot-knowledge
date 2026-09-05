#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
PLATFORM="$ROOT/platform"
PY="$PLATFORM/.venv/bin/python"
if [[ ! -x "$PY" ]]; then
  echo "venv missing — run scripts/install_deps.sh first" >&2
  exit 1
fi
exec "$PY" "$PLATFORM/daemon.py" start "$@"
