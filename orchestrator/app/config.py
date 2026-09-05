"""Application configuration from environment."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic_settings import BaseSettings, SettingsConfigDict


def _repo_root() -> Path:
    # orchestrator/app/config.py -> repo root
    return Path(__file__).resolve().parent.parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = "sqlite:///./data/avrone.db"
    max_agent_depth: int = 3
    allow_agent_execution: bool = False

    # LLM via LiteLLM proxy (default gateway)
    llm_base_url: str = "http://127.0.0.1:4000/v1"
    llm_api_key: str = "sk-avrone"
    llm_model: str = "mock-gpt"

    source_default: str = "avrone-duekrey"
    host: str = "0.0.0.0"
    port: int = 9100

    # Custom / public base URL for HUD + API links
    custom_url: str = ""
    avrone_base_url: str = "http://127.0.0.1:9100"

    # Service ports (daemon-managed)
    litellm_port: int = 4000
    vllm_port: int = 8000
    orchestrator_port: int = 9100
    compat_port: int = 9101
    artifact_port: int = 9102

    # Feature flags
    feature_chat: bool = True
    feature_spawn_agent: bool = True
    feature_builds: bool = True
    feature_artifacts: bool = True
    feature_tool_shell: bool = False  # gated unless ALLOW_AGENT_EXECUTION

    # Paths
    knowledge_root: str = ""
    artifacts_dir: str = ""

    # Shell tool allowlist (comma-separated prefixes)
    shell_allowlist: str = "ls,pwd,echo,cat,head,tail,wc,rg,python3,pytest"

    def resolved_knowledge_root(self) -> Path:
        if self.knowledge_root:
            return Path(self.knowledge_root).resolve()
        return _repo_root()

    def resolved_artifacts_dir(self) -> Path:
        if self.artifacts_dir:
            p = Path(self.artifacts_dir)
        else:
            p = Path(__file__).resolve().parent.parent / "data" / "artifacts"
        p.mkdir(parents=True, exist_ok=True)
        return p

    def public_base_url(self) -> str:
        if self.custom_url:
            return self.custom_url.rstrip("/")
        return self.avrone_base_url.rstrip("/")

    def feature_flags(self) -> dict[str, bool]:
        return {
            "chat": self.feature_chat,
            "spawn_agent": self.feature_spawn_agent,
            "builds": self.feature_builds,
            "artifacts": self.feature_artifacts,
            "tool_shell": self.feature_tool_shell or self.allow_agent_execution,
            "allow_agent_execution": self.allow_agent_execution,
        }

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "product": "ChatBot Avrone Due'Krey",
            "custom_url": self.custom_url,
            "avrone_base_url": self.avrone_base_url,
            "public_base_url": self.public_base_url(),
            "ports": {
                "vllm": self.vllm_port,
                "litellm": self.litellm_port,
                "orchestrator": self.orchestrator_port,
                "compat": self.compat_port,
                "artifacts": self.artifact_port,
            },
            "llm_base_url": self.llm_base_url,
            "llm_model": self.llm_model,
            "max_agent_depth": self.max_agent_depth,
            "allow_agent_execution": self.allow_agent_execution,
            "feature_flags": self.feature_flags(),
            "shell_allowlist": [
                s.strip() for s in self.shell_allowlist.split(",") if s.strip()
            ],
        }


@lru_cache
def get_settings() -> Settings:
    return Settings()
