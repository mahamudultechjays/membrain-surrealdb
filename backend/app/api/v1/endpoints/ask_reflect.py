"""Ask in reflect mode: a synthesis across every scope the signed-in user may read.

Each question stands alone (no session), and nothing is saved: the answer is the
model's own conclusion, which in tests on 2026-11-04 reframed and added claims.
"""

import time

from fastapi import APIRouter, HTTPException, Request, status

from app.api.deps import AccessServiceDep, CurrentUserDep, MemoryReflectDep
from app.domain.errors import MemoryNotConfiguredError, MemoryUnavailableError, ScopeNotGrantedError
from app.schemas.reflect import ReflectRequest, ReflectResponse
from app.services import chat_flow, logger

router = APIRouter(prefix="/ask")


@router.post(
    "/reflect",
    response_model=ReflectResponse,
    responses={
        status.HTTP_403_FORBIDDEN: {"description": "A scope the user can't read"},
        status.HTTP_503_SERVICE_UNAVAILABLE: {"description": "Agent Memory failing"},
    },
)
async def reflect(
    body: ReflectRequest,
    request: Request,
    user: CurrentUserDep,
    access: AccessServiceDep,
    memory: MemoryReflectDep,
) -> ReflectResponse:
    """Answer a synthesis question from the user's readable scopes, with its evidence."""
    try:
        plan = chat_flow.plan_access(
            user.email, await access.readable(user.email), wanted=body.scopes
        )
    except ScopeNotGrantedError as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, f"Not readable: {exc}") from exc

    started = time.perf_counter()
    try:
        result = await memory.reflect(body.question, access=plan)
    except MemoryNotConfiguredError as exc:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Agent Memory is not configured. Set AGENT_MEMORY_* in .env.",
        ) from exc
    except MemoryUnavailableError as exc:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, f"Agent Memory call failed: {exc}"
        ) from exc

    trace_id = getattr(request.state, "trace_id", None)
    # Reflection traces keep no answer text, so the log holds the start of it.
    logger.log(
        "[REFLECT]",
        trace_id=trace_id,
        user=user.email,
        scopes=",".join(plan.read),
        q=repr(body.question[:80]),
        evidence=len(result.evidence),
        latency_ms=round((time.perf_counter() - started) * 1000),
        memory_trace=result.trace_id,
        answer=repr(result.text[:300]),
    )
    return ReflectResponse(
        answer=result.text,
        evidence=result.evidence,
        scopes=list(plan.read),
        trace_id=result.trace_id,
    )
