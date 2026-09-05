"""Tests for spawn-agent, knowledge, config, artifacts, chat."""

from __future__ import annotations

import io


def test_spawn_agent_creates_job(client):
    r = client.post(
        "/spawn-agent",
        json={
            "role": "researcher",
            "goal": "Survey Avrone Due'Krey architecture",
            "tools": ["knowledge_read", "artifact_write"],
        },
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["gated"] is True
    assert body["job_id"]
    assert body["agent"]["role"] == "researcher"
    assert "knowledge_read" in body["tools"]


def test_spawn_agent_into_existing_job(client):
    job = client.post("/jobs", json={"goal": "Parent"}).json()
    r = client.post(
        "/spawn-agent",
        json={
            "role": "coder",
            "goal": "Implement HUD",
            "job_id": job["id"],
            "tools": ["shell"],
        },
    )
    assert r.status_code == 201
    assert r.json()["job_id"] == job["id"]
    assert r.json()["agent"]["role"] == "coder"


def test_knowledge_list_and_read(client):
    r = client.get("/knowledge")
    assert r.status_code == 200
    data = r.json()
    names = {f["name"] for f in data["files"]}
    assert "knowledge.json" in names
    assert "PROFILE.md" in names
    assert "FIRST_TASK.md" in names

    r2 = client.get("/knowledge/knowledge.json")
    assert r2.status_code == 200
    body = r2.json()
    assert body["ok"] is True
    assert "json" in body or "content" in body


def test_knowledge_profile(client):
    r = client.get("/knowledge/PROFILE.md")
    assert r.status_code == 200
    assert r.json()["ok"] is True
    assert "PROFILE" in r.json()["name"] or "content" in r.json()


def test_config_get_put(client):
    r = client.get("/config")
    assert r.status_code == 200
    cfg = r.json()
    assert cfg["product"].startswith("ChatBot Avrone")
    assert "ports" in cfg
    assert cfg["ports"]["orchestrator"] == 9100

    r2 = client.put(
        "/config",
        json={"custom_url": "https://avrone.example.com", "feature_chat": True},
    )
    assert r2.status_code == 200
    updated = r2.json()
    assert updated["custom_url"] == "https://avrone.example.com"
    assert updated["public_base_url"] == "https://avrone.example.com"


def test_artifacts_upload_list_download(client):
    content = b"hello avrone artifact"
    r = client.post(
        "/artifacts/upload",
        files={"file": ("note.txt", io.BytesIO(content), "text/plain")},
    )
    assert r.status_code == 201, r.text
    meta = r.json()
    assert meta["filename"] == "note.txt"
    assert meta["bytes"] == len(content)

    listed = client.get("/artifacts").json()
    assert any(a["filename"] == "note.txt" for a in listed)

    dl = client.get("/artifacts/note.txt")
    assert dl.status_code == 200
    assert dl.content == content


def test_artifacts_write_json(client):
    r = client.post(
        "/artifacts/write",
        json={"filename": "ops.md", "content": "# Avrone\n"},
    )
    assert r.status_code == 200
    assert r.json()["ok"] is True


def test_chat(client):
    r = client.post("/chat", json={"message": "Status of Sub-Agent Orchestration?"})
    assert r.status_code == 200
    data = r.json()
    assert data["reply"]
    assert data["gated"] is True
    assert "Avrone" in data["meta"].get("product", "") or data["model"]


def test_chat_stream(client):
    with client.stream(
        "POST",
        "/chat/stream",
        json={"message": "ping", "stream": True},
    ) as r:
        assert r.status_code == 200
        body = b"".join(r.iter_bytes()).decode()
    assert "data:" in body
    assert "done" in body or "token" in body


def test_builds_queue(client):
    r = client.post(
        "/builds",
        json={"name": "demo-app", "target": "docker", "spec": {"tag": "latest"}},
    )
    assert r.status_code == 201, r.text
    data = r.json()
    assert data["build"]["name"] == "demo-app"
    assert data["job_id"]
    listed = client.get("/builds").json()
    assert any(b["id"] == data["build"]["id"] for b in listed["builds"])


def test_tools_list(client):
    r = client.get("/tools")
    assert r.status_code == 200
    names = {t["name"] for t in r.json()["tools"]}
    assert {"shell", "http_fetch", "knowledge_read", "artifact_write", "spawn_child"} <= names
