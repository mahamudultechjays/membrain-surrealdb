"""Health check schemas."""

from typing import Literal

from pydantic import BaseModel


class HealthResponse(BaseModel):
    """Liveness: the API process is up."""

    status: Literal["ok"]
    version: str
    environment: str


class ReadinessResponse(BaseModel):
    """Readiness: the API and its dependencies can serve traffic."""

    status: Literal["ok", "unavailable"]
    database: Literal["ok", "unavailable"]
