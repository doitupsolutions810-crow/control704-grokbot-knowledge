"""Health endpoint."""

from fastapi import APIRouter

from app import __version__
from app.config import get_settings
from app.schemas import HealthOut

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthOut)
def health() -> HealthOut:
    settings = get_settings()
    return HealthOut(
        status="ok",
        allow_agent_execution=settings.allow_agent_execution,
        max_agent_depth=settings.max_agent_depth,
        version=__version__,
    )
