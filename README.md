# Control704 Grok Bot knowledge pack

Private ingest pack for a Grok Bot named **Wheelhouse**.

Grok Bot has no import API from this workspace. Load the Bot by:

1. Open Grok Bot (cursor.com/dashboard/bot or the Grok Bot app).
2. New → Create new agent.
3. Edit Profile using PROFILE.md.
4. Attach SYSTEM.md (wheelhouse tree), knowledge.json, and FIRST_TASK.md.
5. Send the first task in FIRST_TASK.md.
6. Optional: connect the GitHub connector to this repository so the Bot can reread the pack.

Do not commit .env or provider keys.


---

## Self-hosted platform: ChatBot Avrone Due'Krey

This repository also contains a full self-hosted multi-agent stack:

- **UI:** ChatBot Avrone Due'Krey HUD (`orchestrator/` → http://127.0.0.1:9100/)
- **Features:** Sub-Agent Orchestration · Spawn-Agent for Tasks
- **Daemon:** `platform/daemon.py` (`avrone-duekrey-daemon` / `avrone-host`)

```bash
platform/scripts/install_deps.sh
platform/scripts/start.sh
platform/scripts/status.sh
```

Ports: **8000** vLLM shim · **4000** LiteLLM · **9100** orchestrator/HUD · **9101** compat · **9102** artifacts.

See `platform/README.md` and `orchestrator/README.md`. Knowledge pack files at repo root (`FIRST_TASK.md`, `PROFILE.md`, `knowledge.json`) are preserved and exposed via `/knowledge`.
