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
    tools: list[str] = Field(default_factory=list)


class SpawnAgentRequest(BaseModel):
    """Task-oriented Spawn-Agent for Tasks (top-level alias)."""

    role: str = Field(..., pattern="^(researcher|coder|verifier|orchestrator)$")
    goal: str = Field(..., min_length=1)
    tools: list[str] = Field(default_factory=list)
    job_id: Optional[str] = None
    parent_agent_id: Optional[str] = None
    priority: int = 0
    source: Optional[str] = "spawn-agent"


class ChatMessage(BaseModel):
    role: str = Field(..., pattern="^(system|user|assistant)$")
    content: str = Field(..., min_length=1)


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1)
    history: list[ChatMessage] = Field(default_factory=list)
    job_id: Optional[str] = None
    stream: bool = False
    model: Optional[str] = None


class ChatResponse(BaseModel):
    reply: str
    job_id: Optional[str] = None
    model: str
    gated: bool = False
    meta: dict[str, Any] = Field(default_factory=dict)


class BuildCreate(BaseModel):
    name: str = Field(..., min_length=1)
    target: str = Field(default="app", min_length=1)
    spec: dict[str, Any] = Field(default_factory=dict)
    priority: int = 0


class ConfigUpdate(BaseModel):
    custom_url: Optional[str] = None
    avrone_base_url: Optional[str] = None
    llm_base_url: Optional[str] = None
    llm_model: Optional[str] = None
    llm_api_key: Optional[str] = None
    allow_agent_execution: Optional[bool] = None
    max_agent_depth: Optional[int] = None
    feature_chat: Optional[bool] = None
    feature_spawn_agent: Optional[bool] = None
    feature_builds: Optional[bool] = None
    feature_artifacts: Optional[bool] = None
    feature_tool_shell: Optional[bool] = None
    ports: Optional[dict[str, int]] = None


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
    tools: list[str] = Field(default_factory=list)
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
    job_id: Optional[str] = None
    tools: list[str] = Field(default_factory=list)


class HealthOut(BaseModel):
    status: str
    product: str = "ChatBot Avrone Due'Krey"
    allow_agent_execution: bool
    max_agent_depth: int
    version: str
    llm_base_url: Optional[str] = None
    ports: Optional[dict[str, int]] = None


class MessageOut(BaseModel):
    ok: bool
    message: str
    job: Optional[JobOut] = None


class ArtifactOut(BaseModel):
    filename: str
    bytes: int
    modified_at: str
    download_url: str


class ToolCallRequest(BaseModel):
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
