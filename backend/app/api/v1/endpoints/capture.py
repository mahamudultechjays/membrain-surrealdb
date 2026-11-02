"""Capture endpoints: preview or store what Agent Memory extracts from text."""

from collections.abc import Awaitable

from fastapi import APIRouter, HTTPException, status

from app.api.deps import MemoryCaptureDep
from app.domain.errors import MemoryNotConfiguredError, MemoryUnavailableError
from app.domain.ports.memory_capture import CaptureResult
from app.schemas.capture import CaptureRequest, CaptureResponse

router = APIRouter(prefix="/capture")

_ERRORS: dict[int | str, dict[str, str]] = {
    status.HTTP_503_SERVICE_UNAVAILABLE: {"description": "Agent Memory not configured or failing"}
}


@router.post("/preview", response_model=CaptureResponse, responses=_ERRORS)
async def preview(body: CaptureRequest, capture: MemoryCaptureDep) -> CaptureResponse:
    """What Agent Memory would extract from the text. Nothing is saved."""
    return await _run(capture.preview(body.text))


@router.post("", response_model=CaptureResponse, responses=_ERRORS)
async def store(body: CaptureRequest, capture: MemoryCaptureDep) -> CaptureResponse:
    """Save the text to Agent Memory and return what it extracted."""
    return await _run(capture.store(body.text))


async def _run(call: Awaitable[CaptureResult]) -> CaptureResponse:
    try:
        result = await call
    except MemoryNotConfiguredError as exc:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Agent Memory is not configured. Set AGENT_MEMORY_* in .env.",
        ) from exc
    except MemoryUnavailableError as exc:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, f"Agent Memory call failed: {exc}"
        ) from exc
    return CaptureResponse.model_validate(result)
