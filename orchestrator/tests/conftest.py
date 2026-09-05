"""Pytest fixtures for ChatBot Avrone Due'Krey Orchestrator."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

# Ensure test env before app imports settings
os.environ["ALLOW_AGENT_EXECUTION"] = "false"
os.environ["MAX_AGENT_DEPTH"] = "3"
os.environ["SOURCE_DEFAULT"] = "avrone-duekrey"
os.environ["LLM_BASE_URL"] = "http://127.0.0.1:4000/v1"
os.environ["LLM_MODEL"] = "mock-gpt"

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
os.environ["KNOWLEDGE_ROOT"] = str(REPO_ROOT)

TEST_DB = Path(__file__).resolve().parent.parent / "data" / "test_avrone.db"
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DB}"


@pytest.fixture(autouse=True)
def fresh_db(tmp_path, monkeypatch):
    """Isolate each test with a fresh SQLite database and reset settings cache."""
    db_file = tmp_path / "test.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_file}")
    monkeypatch.setenv("ALLOW_AGENT_EXECUTION", "false")
    monkeypatch.setenv("MAX_AGENT_DEPTH", "3")
    monkeypatch.setenv("SOURCE_DEFAULT", "avrone-duekrey")
    monkeypatch.setenv("KNOWLEDGE_ROOT", str(REPO_ROOT))
    monkeypatch.setenv("ARTIFACTS_DIR", str(tmp_path / "artifacts"))

    from app.config import get_settings
    from app.llm import reset_llm_provider, set_llm_provider, MockLLMProvider
    from app import db

    get_settings.cache_clear()
    reset_llm_provider()
    set_llm_provider(MockLLMProvider())
    db.init_db()
    yield
    get_settings.cache_clear()
    reset_llm_provider()


@pytest.fixture
def client(fresh_db):
    from app.main import app

    with TestClient(app) as c:
        yield c


@pytest.fixture
def exec_enabled(monkeypatch, fresh_db):
    """Enable real LLM path but keep MockLLMProvider."""
    monkeypatch.setenv("ALLOW_AGENT_EXECUTION", "true")
    from app.config import get_settings
    from app.llm import reset_llm_provider, set_llm_provider, MockLLMProvider

    get_settings.cache_clear()
    reset_llm_provider()
    mock = MockLLMProvider(response="mock execution result")
    set_llm_provider(mock)
    yield mock
    get_settings.cache_clear()
    reset_llm_provider()
