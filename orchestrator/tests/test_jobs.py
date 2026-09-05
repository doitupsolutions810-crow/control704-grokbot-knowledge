"""Tests for job lifecycle: create, append, get, events, cancel, health, dashboard."""

from __future__ import annotations


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "ok"
    assert data["allow_agent_execution"] is False
    assert data["max_agent_depth"] == 3
    assert "version" in data


def test_create_job(client):
    r = client.post(
        "/jobs",
        json={"goal": "Ship multi-agent orchestrator", "priority": 1},
    )
    assert r.status_code == 201
    data = r.json()
    assert data["goal"] == "Ship multi-agent orchestrator"
    assert data["status"] == "running"
    assert data["source"] == "grokbot-orchestrator"
    assert data["priority"] == 1
    assert data["root_agent_id"]
    assert len(data["agents"]) >= 1
    root = data["agents"][0]
    assert root["role"] == "orchestrator"
    assert root["depth"] == 0
    # Gated by default
    assert root["status"] == "gated"
    assert data["agent_tree"] is not None
    assert data["agent_tree"]["role"] == "orchestrator"


def test_create_job_custom_source(client):
    r = client.post(
        "/jobs",
        json={"goal": "Custom source job", "source": "ops-console", "tenant_id": "t1"},
    )
    assert r.status_code == 201
    data = r.json()
    assert data["source"] == "ops-console"
    assert data["tenant_id"] == "t1"


def test_get_job(client):
    created = client.post("/jobs", json={"goal": "Inspect me"}).json()
    r = client.get(f"/jobs/{created['id']}")
    assert r.status_code == 200
    assert r.json()["id"] == created["id"]
    assert r.json()["agent_tree"]["id"] == created["root_agent_id"]


def test_get_job_404(client):
    r = client.get("/jobs/job_nonexistent")
    assert r.status_code == 404


def test_list_agents(client):
    created = client.post("/jobs", json={"goal": "Agents list"}).json()
    r = client.get(f"/jobs/{created['id']}/agents")
    assert r.status_code == 200
    agents = r.json()
    assert len(agents) == 1
    assert agents[0]["role"] == "orchestrator"


def test_events_paginated(client):
    created = client.post("/jobs", json={"goal": "Events"}).json()
    r = client.get(f"/jobs/{created['id']}/events", params={"offset": 0, "limit": 10})
    assert r.status_code == 200
    page = r.json()
    assert page["total"] >= 2
    assert len(page["items"]) >= 2
    types = {e["event_type"] for e in page["items"]}
    assert "job.created" in types
    assert "agent.spawned" in types
    assert "agent.gated" in types


def test_append(client):
    created = client.post("/jobs", json={"goal": "Initial goal"}).json()
    r = client.post(
        f"/jobs/{created['id']}/append",
        json={"text": "Also check latency budgets"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    events = client.get(f"/jobs/{created['id']}/events").json()
    assert any(e["event_type"] == "operator.append" for e in events["items"])


def test_cancel(client):
    created = client.post("/jobs", json={"goal": "Cancel me"}).json()
    r = client.post(f"/jobs/{created['id']}/cancel")
    assert r.status_code == 200
    assert r.json()["ok"] is True
    job = client.get(f"/jobs/{created['id']}").json()
    assert job["status"] == "cancelled"
    assert all(a["status"] == "cancelled" for a in job["agents"])


def test_append_after_cancel_fails(client):
    created = client.post("/jobs", json={"goal": "No append"}).json()
    client.post(f"/jobs/{created['id']}/cancel")
    r = client.post(f"/jobs/{created['id']}/append", json={"text": "too late"})
    assert r.status_code == 400


def test_dashboard(client):
    client.post("/jobs", json={"goal": "Dashboard job"})
    r = client.get("/")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    assert b"GrokBot Orchestrator" in r.content
    assert b"Dashboard job" in r.content


def test_execution_enabled_completes_agent(client, exec_enabled):
    r = client.post("/jobs", json={"goal": "Run with mock LLM"})
    assert r.status_code == 201
    data = r.json()
    root = data["agents"][0]
    assert root["status"] == "completed"
    assert root["result"] == "mock execution result"
    assert len(exec_enabled.calls) >= 1
