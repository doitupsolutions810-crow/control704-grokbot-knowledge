"""SQLite database layer."""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Generator, Optional

from app.config import get_settings
from app.models import Agent, Event, Job, new_id, utcnow


def _db_path() -> Path:
    settings = get_settings()
    url = settings.database_url
    if url.startswith("sqlite:///"):
        path = Path(url.replace("sqlite:///", "", 1))
    else:
        path = Path("./data/grokbot.db")
    if not path.is_absolute():
        # Resolve relative to project root (parent of app/)
        root = Path(__file__).resolve().parent.parent
        path = root / path
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(str(_db_path()), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def db_session() -> Generator[sqlite3.Connection, None, None]:
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY,
    goal TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    priority INTEGER NOT NULL DEFAULT 0,
    tenant_id TEXT,
    source TEXT NOT NULL,
    policy TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    root_agent_id TEXT
);

CREATE TABLE IF NOT EXISTS agents (
    id TEXT PRIMARY KEY,
    job_id TEXT NOT NULL,
    role TEXT NOT NULL,
    goal TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    parent_agent_id TEXT,
    depth INTEGER NOT NULL DEFAULT 0,
    activation_intent TEXT,
    result TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (job_id) REFERENCES jobs(id),
    FOREIGN KEY (parent_agent_id) REFERENCES agents(id)
);

CREATE TABLE IF NOT EXISTS events (
    id TEXT PRIMARY KEY,
    job_id TEXT NOT NULL,
    agent_id TEXT,
    event_type TEXT NOT NULL,
    payload TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    FOREIGN KEY (job_id) REFERENCES jobs(id)
);

CREATE INDEX IF NOT EXISTS idx_agents_job ON agents(job_id);
CREATE INDEX IF NOT EXISTS idx_events_job ON events(job_id);
CREATE INDEX IF NOT EXISTS idx_events_created ON events(created_at);
"""


def init_db() -> None:
    with db_session() as conn:
        conn.executescript(SCHEMA)


def reset_db() -> None:
    path = _db_path()
    if path.exists():
        path.unlink()
    init_db()


# --- Job CRUD ---

def insert_job(job: Job) -> Job:
    with db_session() as conn:
        conn.execute(
            """
            INSERT INTO jobs (id, goal, status, priority, tenant_id, source, policy,
                              created_at, updated_at, root_agent_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                job.id, job.goal, job.status, job.priority, job.tenant_id,
                job.source, job.policy, job.created_at, job.updated_at, job.root_agent_id,
            ),
        )
    return job


def get_job(job_id: str) -> Optional[Job]:
    with db_session() as conn:
        row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    return _row_to_job(row) if row else None


def update_job(job_id: str, **fields: Any) -> Optional[Job]:
    if not fields:
        return get_job(job_id)
    fields["updated_at"] = utcnow()
    cols = ", ".join(f"{k} = ?" for k in fields)
    vals = list(fields.values()) + [job_id]
    with db_session() as conn:
        conn.execute(f"UPDATE jobs SET {cols} WHERE id = ?", vals)
    return get_job(job_id)


def list_jobs(limit: int = 100) -> list[Job]:
    with db_session() as conn:
        rows = conn.execute(
            "SELECT * FROM jobs ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
    return [_row_to_job(r) for r in rows]


def _row_to_job(row: sqlite3.Row) -> Job:
    return Job(
        id=row["id"],
        goal=row["goal"],
        status=row["status"],
        priority=row["priority"],
        tenant_id=row["tenant_id"],
        source=row["source"],
        policy=row["policy"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        root_agent_id=row["root_agent_id"],
    )


# --- Agent CRUD ---

def insert_agent(agent: Agent) -> Agent:
    with db_session() as conn:
        conn.execute(
            """
            INSERT INTO agents (id, job_id, role, goal, status, parent_agent_id, depth,
                                activation_intent, result, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                agent.id, agent.job_id, agent.role, agent.goal, agent.status,
                agent.parent_agent_id, agent.depth, agent.activation_intent,
                agent.result, agent.created_at, agent.updated_at,
            ),
        )
    return agent


def get_agent(agent_id: str) -> Optional[Agent]:
    with db_session() as conn:
        row = conn.execute("SELECT * FROM agents WHERE id = ?", (agent_id,)).fetchone()
    return _row_to_agent(row) if row else None


def update_agent(agent_id: str, **fields: Any) -> Optional[Agent]:
    if not fields:
        return get_agent(agent_id)
    fields["updated_at"] = utcnow()
    cols = ", ".join(f"{k} = ?" for k in fields)
    vals = list(fields.values()) + [agent_id]
    with db_session() as conn:
        conn.execute(f"UPDATE agents SET {cols} WHERE id = ?", vals)
    return get_agent(agent_id)


def list_agents_for_job(job_id: str) -> list[Agent]:
    with db_session() as conn:
        rows = conn.execute(
            "SELECT * FROM agents WHERE job_id = ? ORDER BY created_at ASC", (job_id,)
        ).fetchall()
    return [_row_to_agent(r) for r in rows]


def _row_to_agent(row: sqlite3.Row) -> Agent:
    return Agent(
        id=row["id"],
        job_id=row["job_id"],
        role=row["role"],
        goal=row["goal"],
        status=row["status"],
        parent_agent_id=row["parent_agent_id"],
        depth=row["depth"],
        activation_intent=row["activation_intent"],
        result=row["result"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


# --- Event CRUD ---

def insert_event(
    job_id: str,
    event_type: str,
    payload: dict[str, Any] | None = None,
    agent_id: Optional[str] = None,
) -> Event:
    event = Event(
        id=new_id("evt_"),
        job_id=job_id,
        agent_id=agent_id,
        event_type=event_type,
        payload=json.dumps(payload or {}),
    )
    with db_session() as conn:
        conn.execute(
            """
            INSERT INTO events (id, job_id, agent_id, event_type, payload, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                event.id, event.job_id, event.agent_id, event.event_type,
                event.payload, event.created_at,
            ),
        )
    return event


def list_events(
    job_id: str,
    offset: int = 0,
    limit: int = 50,
) -> tuple[list[Event], int]:
    with db_session() as conn:
        total = conn.execute(
            "SELECT COUNT(*) FROM events WHERE job_id = ?", (job_id,)
        ).fetchone()[0]
        rows = conn.execute(
            """
            SELECT * FROM events WHERE job_id = ?
            ORDER BY created_at ASC LIMIT ? OFFSET ?
            """,
            (job_id, limit, offset),
        ).fetchall()
    events = [
        Event(
            id=r["id"],
            job_id=r["job_id"],
            agent_id=r["agent_id"],
            event_type=r["event_type"],
            payload=r["payload"],
            created_at=r["created_at"],
        )
        for r in rows
    ]
    return events, total
