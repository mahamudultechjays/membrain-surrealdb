"""Health check endpoints."""

from fastapi import APIRouter, Response, status

from app.api.deps import MemoryProbeDep
from app.core.config import settings
from app.schemas.health import HealthResponse, ReadinessResponse

router = APIRouter(prefix="/health")


@router.get("", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """Liveness probe: confirms the API process is up. Touches no dependency."""
    return HealthResponse(status="ok", version=settings.VERSION, environment=settings.ENVIRONMENT)


@router.get(
    "/ready",
    response_model=ReadinessResponse,
    responses={status.HTTP_503_SERVICE_UNAVAILABLE: {"model": ReadinessResponse}},
)
async def readiness_check(probe: MemoryProbeDep, response: Response) -> ReadinessResponse:
    """Readiness probe: 503 until Agent Memory is configured and answering."""
    memory = await probe.check()
    if memory == "ok":
        return ReadinessResponse(status="ok", agent_memory=memory)
    response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return ReadinessResponse(status="unavailable", agent_memory=memory)
