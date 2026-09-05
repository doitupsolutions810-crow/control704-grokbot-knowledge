"""Sandboxed agent tools: shell, http_fetch, knowledge_read, artifact_write, spawn_child."""

from __future__ import annotations

import asyncio
import json
import re
import shlex
from pathlib import Path
from typing import Any, Awaitable, Callable, Optional
from urllib.parse import urlparse

import httpx

from app.config import get_settings
from app.models import new_id, utcnow

ToolFn = Callable[..., Awaitable[dict[str, Any]]]

# Dangerous patterns blocked even if allowlisted
_SHELL_BLOCK = re.compile(
    r"(rm\s|sudo|chmod|chown|curl\s|wget\s|nc\s|ncat|ssh\s|scp\s|"
    r">\s*/|;\s*rm|&&\s*rm|\|\s*sh|`|\$\(|eval|exec\s|python\s+-c|"
    r"pip\s+install|apt\s|docker\s|kill\s|pkill|reboot|shutdown)",
    re.IGNORECASE,
)


async def tool_shell(command: str, cwd: Optional[str] = None, **_: Any) -> dict[str, Any]:
    """Run a sandboxed shell command against an allowlist."""
    settings = get_settings()
    if not (settings.feature_tool_shell or settings.allow_agent_execution):
        return {
            "ok": False,
            "gated": True,
            "error": "shell tool gated: set ALLOW_AGENT_EXECUTION=true or FEATURE_TOOL_SHELL=true",
        }

    cmd = (command or "").strip()
    if not cmd:
        return {"ok": False, "error": "empty command"}
    if _SHELL_BLOCK.search(cmd):
        return {"ok": False, "error": "command blocked by safety filter"}

    allow = {s.strip() for s in settings.shell_allowlist.split(",") if s.strip()}
    try:
        parts = shlex.split(cmd)
    except ValueError as exc:
        return {"ok": False, "error": f"parse error: {exc}"}
    if not parts:
        return {"ok": False, "error": "empty command"}
    binary = Path(parts[0]).name
    if binary not in allow:
        return {
            "ok": False,
            "error": f"binary '{binary}' not in allowlist",
            "allowlist": sorted(allow),
        }

    work = Path(cwd) if cwd else settings.resolved_knowledge_root()
    if not work.is_dir():
        work = settings.resolved_knowledge_root()

    try:
        proc = await asyncio.create_subprocess_exec(
            *parts,
            cwd=str(work),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30.0)
    except asyncio.TimeoutError:
        return {"ok": False, "error": "command timed out (30s)"}
    except FileNotFoundError:
        return {"ok": False, "error": f"binary not found: {binary}"}

    return {
        "ok": proc.returncode == 0,
        "returncode": proc.returncode,
        "stdout": stdout.decode("utf-8", errors="replace")[:8000],
        "stderr": stderr.decode("utf-8", errors="replace")[:4000],
    }


async def tool_http_fetch(
    url: str,
    method: str = "GET",
    headers: Optional[dict[str, str]] = None,
    body: Optional[str] = None,
    **_: Any,
) -> dict[str, Any]:
    """Fetch a public HTTP(S) URL (no private/metadata targets)."""
    parsed = urlparse(url or "")
    if parsed.scheme not in ("http", "https"):
        return {"ok": False, "error": "only http/https allowed"}
    host = (parsed.hostname or "").lower()
    blocked = {"localhost", "127.0.0.1", "0.0.0.0", "::1", "metadata.google.internal"}
    if host in blocked or host.startswith("169.254.") or host.startswith("10."):
        return {"ok": False, "error": f"host blocked: {host}"}

    try:
        async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
            resp = await client.request(
                method.upper(),
                url,
                headers=headers or {},
                content=body.encode() if body else None,
            )
        text = resp.text[:12000]
        return {
            "ok": resp.is_success,
            "status_code": resp.status_code,
            "headers": dict(list(resp.headers.items())[:20]),
            "body": text,
        }
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


async def tool_knowledge_read(name: str = "knowledge.json", **_: Any) -> dict[str, Any]:
    """Read a knowledge pack file from repo root."""
    settings = get_settings()
    root = settings.resolved_knowledge_root()
    allowed = {
        "knowledge.json": root / "knowledge.json",
        "PROFILE.md": root / "PROFILE.md",
        "FIRST_TASK.md": root / "FIRST_TASK.md",
        "README.md": root / "README.md",
    }
    # also allow short aliases
    aliases = {
        "knowledge": "knowledge.json",
        "profile": "PROFILE.md",
        "first_task": "FIRST_TASK.md",
        "readme": "README.md",
    }
    key = aliases.get(name, name)
    path = allowed.get(key)
    if not path or not path.is_file():
        return {
            "ok": False,
            "error": f"unknown or missing knowledge file: {name}",
            "available": list(allowed.keys()),
        }
    text = path.read_text(encoding="utf-8")
    out: dict[str, Any] = {"ok": True, "name": key, "path": str(path), "content": text}
    if key.endswith(".json"):
        try:
            out["json"] = json.loads(text)
        except json.JSONDecodeError:
            pass
    return out


async def tool_artifact_write(
    filename: str,
    content: str = "",
    encoding: str = "utf-8",
    **_: Any,
) -> dict[str, Any]:
    """Write an artifact under orchestrator/data/artifacts/."""
    settings = get_settings()
    safe = Path(filename).name
    if not safe or safe in (".", "..") or ".." in filename:
        return {"ok": False, "error": "invalid filename"}
    # sanitize
    safe = re.sub(r"[^\w.\-]+", "_", safe)
    if not safe:
        safe = f"artifact_{new_id()}"
    dest = settings.resolved_artifacts_dir() / safe
    data = content.encode(encoding) if isinstance(content, str) else content
    dest.write_bytes(data if isinstance(data, (bytes, bytearray)) else str(data).encode())
    return {
        "ok": True,
        "filename": safe,
        "path": str(dest),
        "bytes": dest.stat().st_size,
        "created_at": utcnow(),
        "download_url": f"/artifacts/{safe}",
    }


async def tool_spawn_child(
    role: str,
    goal: str,
    job_id: Optional[str] = None,
    parent_agent_id: Optional[str] = None,
    tools: Optional[list[str]] = None,
    **_: Any,
) -> dict[str, Any]:
    """Spawn a child agent (delegates to orchestrator spawn path)."""
    from app import orchestrator as orch

    if not job_id:
        created = await orch.create_job(goal=goal, source="spawn_child")
        job_id = created["job"].id
        parent_agent_id = created["job"].root_agent_id

    result = await orch.spawn_subagent(
        job_id=job_id,
        role=role,
        goal=goal,
        parent_agent_id=parent_agent_id,
        tools=tools,
    )
    agent = result["agent"]
    return {
        "ok": True,
        "job_id": job_id,
        "agent": agent.to_dict() if hasattr(agent, "to_dict") else agent,
        "gated": result.get("gated"),
        "message": result.get("message"),
        "tools": tools or [],
    }


TOOL_REGISTRY: dict[str, ToolFn] = {
    "shell": tool_shell,
    "http_fetch": tool_http_fetch,
    "knowledge_read": tool_knowledge_read,
    "artifact_write": tool_artifact_write,
    "spawn_child": tool_spawn_child,
}


def list_tools() -> list[dict[str, str]]:
    return [
        {"name": "shell", "description": "Sandboxed allowlisted shell command"},
        {"name": "http_fetch", "description": "Fetch public HTTP(S) URL"},
        {"name": "knowledge_read", "description": "Read knowledge pack files"},
        {"name": "artifact_write", "description": "Write artifact file"},
        {"name": "spawn_child", "description": "Spawn a child agent for a sub-goal"},
    ]


async def run_tool(name: str, **kwargs: Any) -> dict[str, Any]:
    fn = TOOL_REGISTRY.get(name)
    if not fn:
        return {"ok": False, "error": f"unknown tool: {name}", "available": list(TOOL_REGISTRY)}
    return await fn(**kwargs)
