"""Health check endpoints."""

from fastapi import APIRouter, Response, status

from app.api.deps import DatabaseProbeDep
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
async def readiness_check(probe: DatabaseProbeDep, response: Response) -> ReadinessResponse:
    """Readiness probe: 503 while SurrealDB is unreachable."""
    if await probe.ping():
        return ReadinessResponse(status="ok", database="ok")
    response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return ReadinessResponse(status="unavailable", database="unavailable")
