"""Builds API — queue application build jobs for the daemon."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app import db
from app import orchestrator
from app.config import get_settings
from app.models import new_id
from app.schemas import BuildCreate

router = APIRouter(prefix="/builds", tags=["builds"])


@router.get("")
def list_builds():
    return {"builds": db.list_builds(limit=100)}


@router.post("", status_code=201)
async def create_build(body: BuildCreate):
    settings = get_settings()
    if not settings.feature_builds:
        raise HTTPException(status_code=403, detail="builds feature disabled")

    build_id = new_id("bld_")
    # Create an orchestration job that the daemon / workers can pick up
    detail = await orchestrator.create_job(
        goal=f"Build application '{body.name}' target={body.target}",
        priority=body.priority,
        source="builds-api",
        policy=f"build:{body.target}",
    )
    job = detail["job"]
    build = db.insert_build(
        build_id=build_id,
        name=body.name,
        target=body.target,
        spec=body.spec,
        job_id=job.id,
    )
    db.insert_event(
        job.id,
        "build.queued",
        {"build_id": build_id, "name": body.name, "target": body.target},
    )
    # Mark as running once queued into orchestrator
    build = db.update_build(build_id, status="running")
    return {"build": build, "job_id": job.id, "message": "Build queued"}


@router.get("/{build_id}")
def get_build(build_id: str):
    build = db.get_build(build_id)
    if not build:
        raise HTTPException(status_code=404, detail="Build not found")
    return build
