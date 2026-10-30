"""Health check schemas."""

from typing import Literal

from pydantic import BaseModel

from app.domain.ports.memory_probe import MemoryStatus


class HealthResponse(BaseModel):
    """Liveness: the API process is up."""

    status: Literal["ok"]
    version: str
    environment: str


class ReadinessResponse(BaseModel):
    """Readiness: the API and its dependencies can serve traffic."""

    status: Literal["ok", "unavailable"]
    agent_memory: MemoryStatus
