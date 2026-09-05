"""Knowledge pack API — reads repo-root knowledge files."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query

from app.config import get_settings
from app.tools.registry import tool_knowledge_read

router = APIRouter(prefix="/knowledge", tags=["knowledge"])


@router.get("")
async def list_knowledge():
    settings = get_settings()
    root = settings.resolved_knowledge_root()
    files = []
    for name in ("knowledge.json", "PROFILE.md", "FIRST_TASK.md", "README.md"):
        p = root / name
        files.append(
            {
                "name": name,
                "exists": p.is_file(),
                "bytes": p.stat().st_size if p.is_file() else 0,
                "url": f"/knowledge/{name}",
            }
        )
    return {"root": str(root), "files": files}


@router.get("/{name}")
async def get_knowledge(name: str, raw: bool = Query(False)):
    result = await tool_knowledge_read(name=name)
    if not result.get("ok"):
        raise HTTPException(status_code=404, detail=result.get("error", "not found"))
    if raw:
        return result["content"]
    return result
