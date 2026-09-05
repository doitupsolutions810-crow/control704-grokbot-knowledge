"""Application configuration from environment."""

from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = "sqlite:///./data/grokbot.db"
    max_agent_depth: int = 3
    allow_agent_execution: bool = False
    llm_base_url: str = "http://localhost:11434/v1"
    llm_api_key: str = "sk-stub"
    llm_model: str = "gpt-4o-mini"
    source_default: str = "grokbot-orchestrator"
    host: str = "0.0.0.0"
    port: int = 8000


@lru_cache
def get_settings() -> Settings:
    return Settings()
