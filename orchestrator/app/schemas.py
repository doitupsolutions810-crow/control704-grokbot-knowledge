"""Pydantic v2 request/response schemas."""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


class JobCreate(BaseModel):
    goal: str = Field(..., min_length=1)
    priority: int = 0
    tenant_id: Optional[str] = None
    source: Optional[str] = None
    policy: Optional[str] = None


class JobAppend(BaseModel):
    text: str = Field(..., min_length=1)


class SpawnRequest(BaseModel):
    role: str = Field(..., pattern="^(researcher|coder|verifier|orchestrator)$")
    goal: str = Field(..., min_length=1)
    parent_agent_id: Optional[str] = None


class AgentOut(BaseModel):
    id: str
    job_id: str
    role: str
    goal: str
    status: str
    parent_agent_id: Optional[str] = None
    depth: int = 0
    activation_intent: Optional[str] = None
    result: Optional[str] = None
    created_at: str
    updated_at: str
    children: list["AgentOut"] = Field(default_factory=list)


class JobOut(BaseModel):
    id: str
    goal: str
    status: str
    priority: int = 0
    tenant_id: Optional[str] = None
    source: str
    policy: Optional[str] = None
    created_at: str
    updated_at: str
    root_agent_id: Optional[str] = None
    agents: list[AgentOut] = Field(default_factory=list)
    agent_tree: Optional[AgentOut] = None


class EventOut(BaseModel):
    id: str
    job_id: str
    agent_id: Optional[str] = None
    event_type: str
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: str


class EventsPage(BaseModel):
    items: list[EventOut]
    total: int
    offset: int
    limit: int


class SpawnResult(BaseModel):
    agent: AgentOut
    gated: bool
    activation_intent: Optional[str] = None
    message: str


class HealthOut(BaseModel):
    status: str
    allow_agent_execution: bool
    max_agent_depth: int
    version: str


class MessageOut(BaseModel):
    ok: bool
    message: str
    job: Optional[JobOut] = None
