"""Multi-agent orchestration with gated execution."""

from __future__ import annotations

from typing import Any, Optional

from app.config import get_settings
from app import db
from app.llm import get_llm_provider
from app.models import (
    Agent,
    AgentRole,
    AgentStatus,
    Job,
    JobStatus,
    new_id,
)
from app.schemas import AgentOut


ROLE_SYSTEM_PROMPTS = {
    AgentRole.orchestrator.value: (
        "You are the root orchestrator agent. Decompose the goal, "
        "coordinate sub-agents (researcher, coder, verifier), and synthesize results."
    ),
    AgentRole.researcher.value: (
        "You are a researcher agent. Gather facts, cite sources, and summarize findings."
    ),
    AgentRole.coder.value: (
        "You are a coder agent. Write, review, and explain code to solve the assigned goal."
    ),
    AgentRole.verifier.value: (
        "You are a verifier agent. Check correctness, edge cases, and report pass/fail."
    ),
}


def build_agent_tree(agents: list[Agent], root_id: Optional[str] = None) -> Optional[AgentOut]:
    by_parent: dict[Optional[str], list[Agent]] = {}
    for a in agents:
        by_parent.setdefault(a.parent_agent_id, []).append(a)

    def to_out(agent: Agent) -> AgentOut:
        children = [to_out(c) for c in by_parent.get(agent.id, [])]
        return AgentOut(
            **{k: v for k, v in agent.to_dict().items()},
            children=children,
        )

    if root_id:
        root = next((a for a in agents if a.id == root_id), None)
        if root:
            return to_out(root)

    roots = by_parent.get(None, [])
    if not roots and agents:
        # orphaned tree — pick shallowest
        root = min(agents, key=lambda a: a.depth)
        return to_out(root)
    if roots:
        return to_out(roots[0])
    return None


async def create_job(
    goal: str,
    priority: int = 0,
    tenant_id: Optional[str] = None,
    source: Optional[str] = None,
    policy: Optional[str] = None,
) -> dict[str, Any]:
    settings = get_settings()
    job_id = new_id("job_")
    source = source or settings.source_default

    job = Job(
        id=job_id,
        goal=goal,
        status=JobStatus.running.value,
        priority=priority,
        tenant_id=tenant_id,
        source=source,
        policy=policy,
    )
    db.insert_job(job)

    root = Agent(
        id=new_id("agt_"),
        job_id=job_id,
        role=AgentRole.orchestrator.value,
        goal=goal,
        status=AgentStatus.pending.value,
        parent_agent_id=None,
        depth=0,
    )
    db.insert_agent(root)
    db.update_job(job_id, root_agent_id=root.id)

    db.insert_event(
        job_id,
        "job.created",
        {"goal": goal, "priority": priority, "source": source, "policy": policy},
    )
    db.insert_event(
        job_id,
        "agent.spawned",
        {"role": root.role, "goal": goal, "depth": 0},
        agent_id=root.id,
    )

    activation = await activate_agent(root.id)

    job = db.get_job(job_id)
    agents = db.list_agents_for_job(job_id)
    return {
        "job": job,
        "agents": agents,
        "activation": activation,
        "agent_tree": build_agent_tree(agents, root.id),
    }


async def activate_agent(agent_id: str) -> dict[str, Any]:
    """Activate an agent. When ALLOW_AGENT_EXECUTION is false, gate (dry-run)."""
    settings = get_settings()
    agent = db.get_agent(agent_id)
    if not agent:
        raise ValueError(f"Agent not found: {agent_id}")

    intent = (
        f"Activate {agent.role} agent depth={agent.depth} "
        f"goal={agent.goal!r} via LLM={settings.llm_model}"
    )

    if not settings.allow_agent_execution:
        db.update_agent(
            agent_id,
            status=AgentStatus.gated.value,
            activation_intent=intent,
        )
        db.insert_event(
            agent.job_id,
            "agent.gated",
            {
                "activation_intent": intent,
                "allow_agent_execution": False,
                "dry_run": True,
            },
            agent_id=agent_id,
        )
        agent = db.get_agent(agent_id)
        return {
            "gated": True,
            "activation_intent": intent,
            "agent": agent,
            "message": "Execution gated: ALLOW_AGENT_EXECUTION=false (dry-run)",
        }

    db.update_agent(agent_id, status=AgentStatus.activating.value, activation_intent=intent)
    db.insert_event(
        agent.job_id,
        "agent.activating",
        {"activation_intent": intent},
        agent_id=agent_id,
    )

    system = ROLE_SYSTEM_PROMPTS.get(
        agent.role,
        "You are a helpful multi-agent worker.",
    )
    provider = get_llm_provider()
    try:
        db.update_agent(agent_id, status=AgentStatus.running.value)
        result = await provider.complete(system, agent.goal)
        db.update_agent(
            agent_id,
            status=AgentStatus.completed.value,
            result=result,
        )
        db.insert_event(
            agent.job_id,
            "agent.completed",
            {"result_preview": result[:500]},
            agent_id=agent_id,
        )
        agent = db.get_agent(agent_id)
        return {
            "gated": False,
            "activation_intent": intent,
            "agent": agent,
            "message": "Agent executed via LLM provider",
            "result": result,
        }
    except Exception as exc:
        db.update_agent(agent_id, status=AgentStatus.failed.value, result=str(exc))
        db.insert_event(
            agent.job_id,
            "agent.failed",
            {"error": str(exc)},
            agent_id=agent_id,
        )
        raise


async def append_to_job(job_id: str, text: str) -> dict[str, Any]:
    job = db.get_job(job_id)
    if not job:
        raise ValueError(f"Job not found: {job_id}")
    if job.status in (JobStatus.cancelled.value, JobStatus.completed.value):
        raise ValueError(f"Cannot append to job in status={job.status}")

    db.insert_event(
        job_id,
        "operator.append",
        {"text": text},
    )
    # Nudge root agent with appended context
    if job.root_agent_id:
        root = db.get_agent(job.root_agent_id)
        if root:
            new_goal = f"{root.goal}\n\n[operator append]: {text}"
            db.update_agent(job.root_agent_id, goal=new_goal)
            await activate_agent(job.root_agent_id)

    db.update_job(job_id, status=JobStatus.running.value)
    job = db.get_job(job_id)
    agents = db.list_agents_for_job(job_id)
    return {
        "job": job,
        "agents": agents,
        "agent_tree": build_agent_tree(agents, job.root_agent_id if job else None),
        "message": "Appended operator text",
    }


async def spawn_subagent(
    job_id: str,
    role: str,
    goal: str,
    parent_agent_id: Optional[str] = None,
) -> dict[str, Any]:
    settings = get_settings()
    job = db.get_job(job_id)
    if not job:
        raise ValueError(f"Job not found: {job_id}")
    if job.status == JobStatus.cancelled.value:
        raise ValueError("Cannot spawn on cancelled job")

    parent_id = parent_agent_id or job.root_agent_id
    parent = db.get_agent(parent_id) if parent_id else None
    if parent_id and not parent:
        raise ValueError(f"Parent agent not found: {parent_id}")
    if parent and parent.job_id != job_id:
        raise ValueError("Parent agent does not belong to this job")

    depth = (parent.depth + 1) if parent else 1
    if depth > settings.max_agent_depth:
        raise ValueError(
            f"Max agent depth exceeded: {depth} > MAX_AGENT_DEPTH={settings.max_agent_depth}"
        )

    agent = Agent(
        id=new_id("agt_"),
        job_id=job_id,
        role=role,
        goal=goal,
        status=AgentStatus.pending.value,
        parent_agent_id=parent_id,
        depth=depth,
    )
    db.insert_agent(agent)
    db.insert_event(
        job_id,
        "agent.spawned",
        {"role": role, "goal": goal, "depth": depth, "parent_agent_id": parent_id},
        agent_id=agent.id,
    )

    activation = await activate_agent(agent.id)
    agent = db.get_agent(agent.id)
    return {
        "agent": agent,
        "gated": activation["gated"],
        "activation_intent": activation.get("activation_intent"),
        "message": activation.get("message", "Spawned"),
    }


def cancel_job(job_id: str) -> dict[str, Any]:
    job = db.get_job(job_id)
    if not job:
        raise ValueError(f"Job not found: {job_id}")

    db.update_job(job_id, status=JobStatus.cancelled.value)
    agents = db.list_agents_for_job(job_id)
    for a in agents:
        if a.status not in (
            AgentStatus.completed.value,
            AgentStatus.cancelled.value,
            AgentStatus.failed.value,
        ):
            db.update_agent(a.id, status=AgentStatus.cancelled.value)

    db.insert_event(job_id, "job.cancelled", {})
    job = db.get_job(job_id)
    agents = db.list_agents_for_job(job_id)
    return {
        "job": job,
        "agents": agents,
        "agent_tree": build_agent_tree(agents, job.root_agent_id if job else None),
        "message": "Job cancelled",
    }


def get_job_detail(job_id: str) -> Optional[dict[str, Any]]:
    job = db.get_job(job_id)
    if not job:
        return None
    agents = db.list_agents_for_job(job_id)
    return {
        "job": job,
        "agents": agents,
        "agent_tree": build_agent_tree(agents, job.root_agent_id),
    }
