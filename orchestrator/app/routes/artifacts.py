"""Artifacts upload / list / download."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import FileResponse

from app.config import get_settings
from app.models import new_id, utcnow
from app.schemas import ArtifactOut
from app.tools.registry import tool_artifact_write

router = APIRouter(prefix="/artifacts", tags=["artifacts"])


def _list_files() -> list[ArtifactOut]:
    settings = get_settings()
    root = settings.resolved_artifacts_dir()
    items: list[ArtifactOut] = []
    for p in sorted(root.iterdir(), key=lambda x: x.stat().st_mtime, reverse=True):
        if not p.is_file() or p.name.startswith("."):
            continue
        mtime = datetime.fromtimestamp(p.stat().st_mtime, tz=timezone.utc).isoformat()
        items.append(
            ArtifactOut(
                filename=p.name,
                bytes=p.stat().st_size,
                modified_at=mtime,
                download_url=f"/artifacts/{p.name}",
            )
        )
    return items


@router.get("", response_model=list[ArtifactOut])
def list_artifacts() -> list[ArtifactOut]:
    settings = get_settings()
    if not settings.feature_artifacts:
        raise HTTPException(status_code=403, detail="artifacts feature disabled")
    return _list_files()


@router.post("/upload", response_model=ArtifactOut, status_code=201)
async def upload_artifact(file: UploadFile = File(...)) -> ArtifactOut:
    settings = get_settings()
    if not settings.feature_artifacts:
        raise HTTPException(status_code=403, detail="artifacts feature disabled")
    raw_name = file.filename or f"upload_{new_id()}"
    safe = re.sub(r"[^\w.\-]+", "_", Path(raw_name).name) or f"upload_{new_id()}"
    dest = settings.resolved_artifacts_dir() / safe
    data = await file.read()
    dest.write_bytes(data)
    return ArtifactOut(
        filename=safe,
        bytes=len(data),
        modified_at=utcnow(),
        download_url=f"/artifacts/{safe}",
    )


@router.post("/write")
async def write_artifact(body: dict):
    """JSON write helper used by agents / HUD."""
    filename = body.get("filename") or f"note_{new_id()}.txt"
    content = body.get("content") or ""
    result = await tool_artifact_write(filename=filename, content=content)
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("error"))
    return result


@router.get("/{filename}")
def download_artifact(filename: str):
    settings = get_settings()
    safe = Path(filename).name
    path = settings.resolved_artifacts_dir() / safe
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Artifact not found")
    return FileResponse(path, filename=safe)
