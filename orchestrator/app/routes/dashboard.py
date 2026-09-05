"""Minimal HTML dashboard."""

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
    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "job_rows": job_rows,
            "allow_exec": settings.allow_agent_execution,
            "max_depth": settings.max_agent_depth,
        },
    )
