"""Tests for spawn + gated execution and depth limits."""

from __future__ import annotations


def test_spawn_gated_by_default(client):
    job = client.post("/jobs", json={"goal": "Parent task"}).json()
    r = client.post(
        f"/jobs/{job['id']}/spawn",
        json={"role": "researcher", "goal": "Find prior art"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["gated"] is True
    assert body["activation_intent"]
    assert "dry-run" in body["message"].lower() or "gated" in body["message"].lower()
    agent = body["agent"]
    assert agent["role"] == "researcher"
    assert agent["status"] == "gated"
    assert agent["depth"] == 1
    assert agent["parent_agent_id"] == job["root_agent_id"]

    agents = client.get(f"/jobs/{job['id']}/agents").json()
    assert len(agents) == 2


def test_spawn_coder_and_verifier(client):
    job = client.post("/jobs", json={"goal": "Build feature"}).json()
    for role, goal in [
        ("coder", "Implement API"),
        ("verifier", "Check tests pass"),
    ]:
        r = client.post(
            f"/jobs/{job['id']}/spawn",
            json={"role": role, "goal": goal},
        )
        assert r.status_code == 200
        assert r.json()["agent"]["role"] == role
        assert r.json()["gated"] is True

    detail = client.get(f"/jobs/{job['id']}").json()
    assert len(detail["agents"]) == 3
    tree = detail["agent_tree"]
    assert tree["role"] == "orchestrator"
    assert len(tree["children"]) == 2


def test_spawn_with_explicit_parent(client):
    job = client.post("/jobs", json={"goal": "Nested"}).json()
    child = client.post(
        f"/jobs/{job['id']}/spawn",
        json={"role": "researcher", "goal": "Layer 1"},
    ).json()["agent"]

    grandchild = client.post(
        f"/jobs/{job['id']}/spawn",
        json={
            "role": "coder",
            "goal": "Layer 2",
            "parent_agent_id": child["id"],
        },
    ).json()["agent"]
    assert grandchild["depth"] == 2
    assert grandchild["parent_agent_id"] == child["id"]


def test_max_depth_enforced(client):
    job = client.post("/jobs", json={"goal": "Deep tree"}).json()
    parent_id = job["root_agent_id"]
    # depth 1, 2, 3 OK; depth 4 should fail (MAX=3)
    for i, role in enumerate(["researcher", "coder", "verifier"], start=1):
        r = client.post(
            f"/jobs/{job['id']}/spawn",
            json={"role": role, "goal": f"d{i}", "parent_agent_id": parent_id},
        )
        assert r.status_code == 200, r.text
        parent_id = r.json()["agent"]["id"]
        assert r.json()["agent"]["depth"] == i

    r = client.post(
        f"/jobs/{job['id']}/spawn",
        json={"role": "researcher", "goal": "too deep", "parent_agent_id": parent_id},
    )
    assert r.status_code == 400
    assert "depth" in r.json()["detail"].lower()


def test_spawn_on_missing_job(client):
    r = client.post(
        "/jobs/job_missing/spawn",
        json={"role": "coder", "goal": "x"},
    )
    assert r.status_code == 404


def test_spawn_invalid_role(client):
    job = client.post("/jobs", json={"goal": "Roles"}).json()
    r = client.post(
        f"/jobs/{job['id']}/spawn",
        json={"role": "hacker", "goal": "nope"},
    )
    assert r.status_code == 422


def test_spawn_cancelled_job(client):
    job = client.post("/jobs", json={"goal": "Cancel then spawn"}).json()
    client.post(f"/jobs/{job['id']}/cancel")
    r = client.post(
        f"/jobs/{job['id']}/spawn",
        json={"role": "researcher", "goal": "late"},
    )
    assert r.status_code == 400


def test_spawn_executes_when_enabled(client, exec_enabled):
    job = client.post("/jobs", json={"goal": "Live spawn"}).json()
    r = client.post(
        f"/jobs/{job['id']}/spawn",
        json={"role": "verifier", "goal": "Verify output"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["gated"] is False
    assert body["agent"]["status"] == "completed"
    assert body["agent"]["result"] == "mock execution result"
