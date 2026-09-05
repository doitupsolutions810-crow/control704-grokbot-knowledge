"""SQLAlchemy-free SQLite models via raw SQL helpers and typed dataclasses."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional
import json
import uuid


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_id(prefix: str = "") -> str:
    uid = uuid.uuid4().hex[:12]
    return f"{prefix}{uid}" if prefix else uid


class JobStatus(str, Enum):
    pending = "pending"
    running = "running"
    completed = "completed"
    cancelled = "cancelled"
    failed = "failed"


class AgentStatus(str, Enum):
    pending = "pending"
    gated = "gated"
    activating = "activating"
    running = "running"
    completed = "completed"
    cancelled = "cancelled"
    failed = "failed"


class AgentRole(str, Enum):
    orchestrator = "orchestrator"
    researcher = "researcher"
    coder = "coder"
    verifier = "verifier"


@dataclass
class Job:
    id: str
    goal: str
    status: str = JobStatus.pending.value
    priority: int = 0
    tenant_id: Optional[str] = None
    source: str = "grokbot-orchestrator"
    policy: Optional[str] = None
    created_at: str = field(default_factory=utcnow)
    updated_at: str = field(default_factory=utcnow)
    root_agent_id: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "goal": self.goal,
            "status": self.status,
            "priority": self.priority,
            "tenant_id": self.tenant_id,
            "source": self.source,
            "policy": self.policy,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "root_agent_id": self.root_agent_id,
        }


@dataclass
class Agent:
    id: str
    job_id: str
    role: str
    goal: str
    status: str = AgentStatus.pending.value
    parent_agent_id: Optional[str] = None
    depth: int = 0
    activation_intent: Optional[str] = None
    result: Optional[str] = None
    created_at: str = field(default_factory=utcnow)
    updated_at: str = field(default_factory=utcnow)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "job_id": self.job_id,
            "role": self.role,
            "goal": self.goal,
            "status": self.status,
            "parent_agent_id": self.parent_agent_id,
            "depth": self.depth,
            "activation_intent": self.activation_intent,
            "result": self.result,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass
class Event:
    id: str
    job_id: str
    agent_id: Optional[str]
    event_type: str
    payload: str  # JSON string
    created_at: str = field(default_factory=utcnow)

    def to_dict(self) -> dict[str, Any]:
        try:
            payload_obj = json.loads(self.payload) if self.payload else {}
        except json.JSONDecodeError:
            payload_obj = {"raw": self.payload}
        return {
            "id": self.id,
            "job_id": self.job_id,
            "agent_id": self.agent_id,
            "event_type": self.event_type,
            "payload": payload_obj,
            "created_at": self.created_at,
        }
