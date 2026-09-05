"""Job orchestration endpoints."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from app import db
from app import orchestrator
from app.schemas import (
    AgentOut,
    EventOut,
    EventsPage,
    JobAppend,
    JobCreate,
    JobOut,
    MessageOut,
    SpawnRequest,
    SpawnResult,
)

router = APIRouter(prefix="/jobs", tags=["jobs"])


def _job_out(detail: dict) -> JobOut:
    job = detail["job"]
    agents = detail.get("agents") or []
    tree = detail.get("agent_tree")
    return JobOut(
        **job.to_dict(),
        agents=[AgentOut(**a.to_dict()) for a in agents],
        agent_tree=tree,
    )


@router.post("", response_model=JobOut, status_code=201)
async def create_job(body: JobCreate) -> JobOut:
    detail = await orchestrator.create_job(
        goal=body.goal,
        priority=body.priority,
        tenant_id=body.tenant_id,
        source=body.source,
        policy=body.policy,
    )
    return _job_out(detail)


@router.get("", response_model=list[JobOut])
def list_jobs(limit: int = Query(50, ge=1, le=200)) -> list[JobOut]:
    jobs = db.list_jobs(limit=limit)
    out = []
    for job in jobs:
        detail = orchestrator.get_job_detail(job.id)
        if detail:
            out.append(_job_out(detail))
    return out


@router.get("/{job_id}", response_model=JobOut)
def get_job(job_id: str) -> JobOut:
    detail = orchestrator.get_job_detail(job_id)
    if not detail:
        raise HTTPException(status_code=404, detail="Job not found")
    return _job_out(detail)


@router.get("/{job_id}/agents", response_model=list[AgentOut])
def get_agents(job_id: str) -> list[AgentOut]:
    if not db.get_job(job_id):
        raise HTTPException(status_code=404, detail="Job not found")
    agents = db.list_agents_for_job(job_id)
    return [AgentOut(**a.to_dict()) for a in agents]


@router.get("/{job_id}/events", response_model=EventsPage)
def get_events(
    job_id: str,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
) -> EventsPage:
    if not db.get_job(job_id):
        raise HTTPException(status_code=404, detail="Job not found")
    events, total = db.list_events(job_id, offset=offset, limit=limit)
    return EventsPage(
        items=[EventOut(**e.to_dict()) for e in events],
        total=total,
        offset=offset,
        limit=limit,
    )


@router.post("/{job_id}/append", response_model=MessageOut)
async def append_job(job_id: str, body: JobAppend) -> MessageOut:
    try:
        detail = await orchestrator.append_to_job(job_id, body.text)
    except ValueError as exc:
        msg = str(exc)
        code = 404 if "not found" in msg.lower() else 400
        raise HTTPException(status_code=code, detail=msg) from exc
    return MessageOut(ok=True, message=detail["message"], job=_job_out(detail))


@router.post("/{job_id}/spawn", response_model=SpawnResult)
async def spawn_agent(job_id: str, body: SpawnRequest) -> SpawnResult:
    try:
        result = await orchestrator.spawn_subagent(
            job_id=job_id,
            role=body.role,
            goal=body.goal,
            parent_agent_id=body.parent_agent_id,
            tools=body.tools,
        )
    except ValueError as exc:
        msg = str(exc)
        code = 404 if "not found" in msg.lower() else 400
        raise HTTPException(status_code=code, detail=msg) from exc

    agent = result["agent"]
    return SpawnResult(
        agent=AgentOut(**agent.to_dict()),
        gated=result["gated"],
        activation_intent=result.get("activation_intent"),
        message=result["message"],
        job_id=job_id,
        tools=result.get("tools") or body.tools,
    )


@router.post("/{job_id}/cancel", response_model=MessageOut)
def cancel_job(job_id: str) -> MessageOut:
    try:
        detail = orchestrator.cancel_job(job_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return MessageOut(ok=True, message=detail["message"], job=_job_out(detail))
