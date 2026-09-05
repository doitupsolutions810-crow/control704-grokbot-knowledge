"""Spawn-Agent for Tasks — top-level alias."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app import orchestrator
from app.config import get_settings
from app.schemas import AgentOut, SpawnAgentRequest, SpawnResult
from app.tools import list_tools

router = APIRouter(tags=["spawn-agent"])


@router.post("/spawn-agent", response_model=SpawnResult, status_code=201)
async def spawn_agent(body: SpawnAgentRequest) -> SpawnResult:
    settings = get_settings()
    if not settings.feature_spawn_agent:
        raise HTTPException(status_code=403, detail="spawn-agent feature disabled")

    try:
        result = await orchestrator.spawn_agent_for_task(
            role=body.role,
            goal=body.goal,
            tools=body.tools,
            job_id=body.job_id,
            parent_agent_id=body.parent_agent_id,
            priority=body.priority,
            source=body.source,
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
        job_id=result.get("job_id"),
        tools=result.get("tools") or body.tools,
    )


@router.get("/tools")
def get_tools():
    return {"tools": list_tools()}
