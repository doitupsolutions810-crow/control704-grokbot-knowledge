#!/usr/bin/env bash
# Install ChatBot Avrone Due'Krey platform + orchestrator dependencies.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
PLATFORM="$ROOT/platform"
ORCH="$ROOT/orchestrator"

echo "==> ChatBot Avrone Due'Krey · install_deps"
echo "    root=$ROOT"

python3 -m venv "$PLATFORM/.venv"
# shellcheck disable=SC1091
source "$PLATFORM/.venv/bin/activate"
pip install -U pip wheel setuptools

echo "==> Installing orchestrator requirements"
pip install -r "$ORCH/requirements.txt"

echo "==> Installing platform requirements"
pip install -r "$PLATFORM/requirements.txt"
pip install -q "litellm[proxy]" backoff || echo "LiteLLM proxy extras optional — mock_litellm.py will be used"

# Share venv with orchestrator for convenience
if [[ ! -e "$ORCH/.venv" ]]; then
  ln -s "$PLATFORM/.venv" "$ORCH/.venv" || true
fi

echo "==> GPU / vLLM check"
if command -v nvidia-smi >/dev/null 2>&1; then
  nvidia-smi || true
  echo "NVIDIA GPU detected — attempting optional vllm install (may take a while)…"
  if pip install 'vllm>=0.5.0'; then
    echo "vLLM installed. Set AVRONE_USE_REAL_VLLM=1 to use it."
  else
    echo "WARNING: vLLM install failed — continuing with protocol shim."
  fi
else
  echo "No nvidia-smi — skipping real vLLM. Using platform/vllm_shim.py (OpenAI-compatible proxy)."
fi

# Try litellm; mock_litellm.py is the fallback
if python -c "import litellm" 2>/dev/null; then
  echo "LiteLLM OK"
else
  echo "LiteLLM import check failed after install — daemon will use mock_litellm.py"
fi

cp -n "$PLATFORM/configs/avrone.env.example" "$PLATFORM/configs/avrone.env" 2>/dev/null || true
cp -n "$ORCH/.env.example" "$ORCH/.env" 2>/dev/null || true

echo "==> Done. Next: platform/scripts/start.sh"
