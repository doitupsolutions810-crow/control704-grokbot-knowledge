"""ChatBot Avrone Due'Krey HUD dashboard."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app import db
from app.config import get_settings

router = APIRouter(tags=["dashboard"])

TEMPLATES_DIR = Path(__file__).resolve().parent.parent.parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


@router.get("/", response_class=HTMLResponse)
def dashboard(request: Request) -> HTMLResponse:
    settings = get_settings()
    jobs = db.list_jobs(limit=50)
    job_rows = []
    for job in jobs:
        agents = db.list_agents_for_job(job.id)
        job_rows.append({"job": job, "agents": agents, "agent_count": len(agents)})
    artifacts_dir = settings.resolved_artifacts_dir()
    artifacts = []
    if artifacts_dir.is_dir():
        for p in sorted(artifacts_dir.iterdir(), key=lambda x: x.stat().st_mtime, reverse=True)[:30]:
            if p.is_file() and not p.name.startswith("."):
                artifacts.append({"name": p.name, "bytes": p.stat().st_size})
    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "job_rows": job_rows,
            "allow_exec": settings.allow_agent_execution,
            "max_depth": settings.max_agent_depth,
            "product": "ChatBot Avrone Due'Krey",
            "public_base_url": settings.public_base_url(),
            "llm_base_url": settings.llm_base_url,
            "llm_model": settings.llm_model,
            "artifacts": artifacts,
            "ports": {
                "vllm": settings.vllm_port,
                "litellm": settings.litellm_port,
                "orchestrator": settings.orchestrator_port,
                "compat": settings.compat_port,
                "artifacts": settings.artifact_port,
            },
            "features": settings.feature_flags(),
        },
    )
