"""Runtime config GET/PUT for custom URL, ports, model routes, feature flags."""

from __future__ import annotations

import json

from fastapi import APIRouter

from app import db
from app.config import get_settings
from app.schemas import ConfigUpdate

router = APIRouter(prefix="/config", tags=["config"])

# In-process overrides applied on top of env settings (persisted in SQLite)
_OVERRIDES: dict = {}


def _apply_overrides(settings_dict: dict) -> dict:
    out = dict(settings_dict)
    for k, v in _OVERRIDES.items():
        if k == "ports" and isinstance(v, dict):
            ports = dict(out.get("ports") or {})
            ports.update(v)
            out["ports"] = ports
        elif k == "feature_flags" and isinstance(v, dict):
            flags = dict(out.get("feature_flags") or {})
            flags.update(v)
            out["feature_flags"] = flags
        else:
            out[k] = v
    if out.get("custom_url"):
        out["public_base_url"] = str(out["custom_url"]).rstrip("/")
    return out


def load_persisted_overrides() -> None:
    global _OVERRIDES
    raw = db.get_runtime_config("avrone_overrides")
    if raw:
        try:
            _OVERRIDES = json.loads(raw)
        except json.JSONDecodeError:
            _OVERRIDES = {}


@router.get("")
def get_config():
    load_persisted_overrides()
    settings = get_settings()
    return _apply_overrides(settings.to_public_dict())


@router.put("")
def put_config(body: ConfigUpdate):
    global _OVERRIDES
    load_persisted_overrides()
    data = body.model_dump(exclude_none=True)
    ports = data.pop("ports", None)

    flag_keys = {
        "feature_chat": "chat",
        "feature_spawn_agent": "spawn_agent",
        "feature_builds": "builds",
        "feature_artifacts": "artifacts",
        "feature_tool_shell": "tool_shell",
    }
    for src, dst in flag_keys.items():
        if src in data:
            _OVERRIDES.setdefault("feature_flags", {})[dst] = data.pop(src)

    if "allow_agent_execution" in data:
        _OVERRIDES.setdefault("feature_flags", {})["allow_agent_execution"] = data[
            "allow_agent_execution"
        ]
        _OVERRIDES["allow_agent_execution"] = data.pop("allow_agent_execution")

    for k, v in data.items():
        _OVERRIDES[k] = v

    if ports:
        _OVERRIDES.setdefault("ports", {}).update(ports)

    db.set_runtime_config("avrone_overrides", json.dumps(_OVERRIDES))

    # Live-apply a few settings into the cached Settings object when possible
    settings = get_settings()
    if "custom_url" in _OVERRIDES:
        settings.custom_url = str(_OVERRIDES["custom_url"])
    if "avrone_base_url" in _OVERRIDES:
        settings.avrone_base_url = str(_OVERRIDES["avrone_base_url"])
    if "llm_base_url" in _OVERRIDES:
        settings.llm_base_url = str(_OVERRIDES["llm_base_url"])
    if "llm_model" in _OVERRIDES:
        settings.llm_model = str(_OVERRIDES["llm_model"])
    if "llm_api_key" in _OVERRIDES:
        settings.llm_api_key = str(_OVERRIDES["llm_api_key"])
    if "max_agent_depth" in _OVERRIDES:
        settings.max_agent_depth = int(_OVERRIDES["max_agent_depth"])
    if "allow_agent_execution" in _OVERRIDES:
        settings.allow_agent_execution = bool(_OVERRIDES["allow_agent_execution"])

    return _apply_overrides(settings.to_public_dict())
