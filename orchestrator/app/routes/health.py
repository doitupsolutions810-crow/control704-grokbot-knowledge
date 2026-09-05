"""Health endpoint."""

from fastapi import APIRouter

from app import __product__, __version__
from app.config import get_settings
from app.schemas import HealthOut

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthOut)
def health() -> HealthOut:
    settings = get_settings()
    return HealthOut(
        status="ok",
        product=__product__,
        allow_agent_execution=settings.allow_agent_execution,
        max_agent_depth=settings.max_agent_depth,
        version=__version__,
        llm_base_url=settings.llm_base_url,
        ports={
            "vllm": settings.vllm_port,
            "litellm": settings.litellm_port,
            "orchestrator": settings.orchestrator_port,
            "compat": settings.compat_port,
            "artifacts": settings.artifact_port,
        },
    )


@router.get("/services")
def services():
    """Service status tiles for the HUD (local probes)."""
    import httpx

    settings = get_settings()
    probes = {
        "orchestrator": f"http://127.0.0.1:{settings.orchestrator_port}/health",
        "litellm": f"http://127.0.0.1:{settings.litellm_port}/health",
        "vllm": f"http://127.0.0.1:{settings.vllm_port}/health",
        "artifacts": f"http://127.0.0.1:{settings.artifact_port}/health",
        "compat": f"http://127.0.0.1:{settings.compat_port}/health",
    }
    status = {}
    for name, url in probes.items():
        try:
            r = httpx.get(url, timeout=0.8)
            status[name] = {
                "ok": r.status_code < 500,
                "status_code": r.status_code,
                "url": url,
            }
        except Exception as exc:
            status[name] = {"ok": False, "error": str(exc), "url": url}
    # Self is always ok if we answered
    status["orchestrator"] = {
        "ok": True,
        "status_code": 200,
        "url": probes["orchestrator"],
        "self": True,
    }
    return {"product": "ChatBot Avrone Due'Krey", "services": status}
