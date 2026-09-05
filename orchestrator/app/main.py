"""ChatBot Avrone Due'Krey Orchestrator FastAPI application."""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app import __product__, __version__, db
from app.routes import (
    artifacts,
    builds,
    chat,
    config_api,
    dashboard,
    health,
    jobs,
    knowledge,
    spawn_agent,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    # Ensure artifacts dir exists
    from app.config import get_settings

    get_settings().resolved_artifacts_dir()
    try:
        from app.routes.config_api import load_persisted_overrides

        load_persisted_overrides()
    except Exception:
        pass
    yield


app = FastAPI(
    title=__product__,
    description=(
        "ChatBot Avrone Due'Krey — Sub-Agent Orchestration and Spawn-Agent for Tasks. "
        "Self-hosted multi-agent control plane with gated execution."
    ),
    version=__version__,
    lifespan=lifespan,
)

app.include_router(health.router)
app.include_router(jobs.router)
app.include_router(chat.router)
app.include_router(spawn_agent.router)
app.include_router(knowledge.router)
app.include_router(builds.router)
app.include_router(config_api.router)
app.include_router(artifacts.router)
app.include_router(dashboard.router)

static_dir = Path(__file__).resolve().parent.parent / "static"
static_dir.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


def create_app() -> FastAPI:
    return app
