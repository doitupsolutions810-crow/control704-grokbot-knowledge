# ChatBot Avrone Due'Krey — Platform (`avrone-host`)

Self-hosted multi-agent stack: **Sub-Agent Orchestration**, **Spawn-Agent for Tasks**, LiteLLM proxy, vLLM OpenAI-compatible shim, artifact server, and the orchestrator HUD.

## Port map

| Port | Service | Notes |
|------|---------|-------|
| **8000** | vLLM shim (`vllm_shim.py`) | OpenAI `/v1/chat/completions`; proxies to LiteLLM when no GPU |
| **4000** | LiteLLM proxy (or `mock_litellm.py`) | Model routes in `configs/litellm_config.yaml` |
| **9100** | Orchestrator API + HUD | Gateway / control plane |
| **9101** | Compat shim (optional) | `/v1/agent` → `/spawn-agent` |
| **9102** | Artifact file server | Static/list for `orchestrator/data/artifacts` |

If a preferred port is busy, `daemon.py` picks the next free port and records it in `platform/run/daemon_state.json`.

## Install

```bash
cd platform
./scripts/install_deps.sh
# creates platform/.venv, installs orchestrator + litellm
# skips real vLLM unless nvidia-smi works
```

Copy env:

```bash
cp configs/avrone.env.example configs/avrone.env
# set CUSTOM_URL, OPENAI_API_KEY, ALLOW_AGENT_EXECUTION as needed
```

## Start / stop / status

```bash
./scripts/start.sh      # start all supervised processes once
./scripts/status.sh
./scripts/stop.sh

# long-running supervisor (restarts crashes):
.venv/bin/python daemon.py supervise
```

Or: `./avrone-daemon start|stop|status|supervise`

HUD: http://127.0.0.1:9100/  
OpenAPI: http://127.0.0.1:9100/docs

## Spawn-Agent for Tasks

```bash
curl -s -X POST http://127.0.0.1:9100/spawn-agent \
  -H 'Content-Type: application/json' \
  -d '{"role":"researcher","goal":"Read knowledge pack","tools":["knowledge_read","artifact_write"]}'
```

Creates a job when `job_id` is omitted; otherwise nests under the given job.

## CUSTOM_URL

Set in `configs/avrone.env` or:

```bash
curl -X PUT http://127.0.0.1:9100/config \
  -H 'Content-Type: application/json' \
  -d '{"custom_url":"https://avrone.example.com"}'
```

## GPU / real vLLM

Box without GPU → **protocol-compatible shim** only (default).

With CUDA:

1. `nvidia-smi` works  
2. `pip install -r requirements-vllm.txt`  
3. `AVRONE_USE_REAL_VLLM=1` + `VLLM_MODEL=...`  
4. Restart daemon (wire real server in place of shim when ready)

## Docker Compose

```bash
cd platform
docker compose up --build
```

## systemd

See `deploy/avrone-daemon.service`.

## Gating

`ALLOW_AGENT_EXECUTION` defaults to **false**. Agents record activation intents and stay `gated` until enabled.


## LiteLLM notes

By default the daemon runs `mock_litellm.py` on `:4000` (reliable OpenAI-compatible stub).  
Set `AVRONE_USE_LITELLM=1` after `pip install 'litellm[proxy]'` to use the real LiteLLM CLI with `configs/litellm_config.yaml`.  
If the real proxy fails health checks, the daemon automatically falls back to the mock.

Unset or avoid pointing LiteLLM at the orchestrator SQLite `DATABASE_URL` — LiteLLM's virtual-key DB wants PostgreSQL.

## Port conflicts

If `:8000` is already taken, the daemon binds the vLLM shim to the next free port (e.g. `8001`) and records it in `platform/run/ports.json` / `daemon_state.json`.
