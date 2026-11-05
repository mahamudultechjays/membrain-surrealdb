"""Ask in reflect mode: one synthesis per layer, with org > team > personal applied.

Each scope the user reads is reflected on separately, in parallel, with a key
that reads only that scope, so each layer's view stays its own. The highest
layer whose reflection drew on evidence applies; the others are overridden.
Each question stands alone and nothing is saved: a reflection is the model's
own conclusion, which in tests on 2026-11-04 reframed and added claims.
"""

import asyncio
import time

from fastapi import APIRouter, HTTPException, Request, status

from app.api.deps import AccessServiceDep, CurrentUserDep, MemoryReflectDep
from app.domain.errors import MemoryNotConfiguredError, ScopeNotGrantedError
from app.domain.ports.memory_chat import ChatAccess, Reflection
from app.domain.ports.user_scopes import LayerName
from app.schemas.reflect import ReflectLayerOut, ReflectRequest, ReflectResponse
from app.services import chat_flow, layers_flow, logger

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
    """Reflect on each readable scope separately and mark which layer applies."""
    readable = await access.readable(user.email)
    try:
        plan = chat_flow.plan_access(user.email, readable, wanted=body.scopes)
    except ScopeNotGrantedError as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, f"Not readable: {exc}") from exc

    layer_of = {g.scope_path: g.layer for g in readable}
    layers: list[tuple[LayerName, str]] = [(layer_of[scope], scope) for scope in plan.read]
    started = time.perf_counter()
    # One key holder per (user, scope), so each key reads only its own scope.
    results: list[Reflection | BaseException] = await asyncio.gather(
        *(
            memory.reflect(
                body.question,
                access=ChatAccess(owner=f"{user.email}|{scope}", read=(scope,), write=plan.write),
            )
            for _, scope in layers
        ),
        return_exceptions=True,
    )
    failures = [r for r in results if isinstance(r, BaseException)]
    if failures and len(failures) == len(results):
        first = failures[0]
        if isinstance(first, MemoryNotConfiguredError):
            raise HTTPException(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                "Agent Memory is not configured. Set AGENT_MEMORY_* in .env.",
            ) from first
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, f"Agent Memory call failed: {first}"
        ) from first

    resolved = layers_flow.resolve(layers, results)
    applies = next((r.scope for r in resolved if r.status == "applies"), None)
    latency_ms = round((time.perf_counter() - started) * 1000)
    trace_id = getattr(request.state, "trace_id", None)
    for r in resolved:
        # Reflection traces keep no answer text, so the log holds the start of it.
        logger.log(
            "[REFLECT]",
            trace_id=trace_id,
            user=user.email,
            layer=r.layer,
            scope=r.scope,
            status=r.status,
            q=repr(body.question[:80]),
            evidence=len(r.reflection.evidence) if r.reflection else None,
            latency_ms=latency_ms,
            memory_trace=r.reflection.trace_id if r.reflection else None,
            error=r.error,
            answer=repr(r.reflection.text[:300]) if r.reflection else None,
        )
    return ReflectResponse(
        layers=[
            ReflectLayerOut(
                layer=r.layer,
                scope=r.scope,
                status=r.status,
                answer=r.reflection.text if r.reflection else None,
                evidence=r.reflection.evidence if r.reflection else [],
                error=r.error,
                trace_id=r.reflection.trace_id if r.reflection else None,
            )
            for r in resolved
        ],
        applies=applies,
        scopes=list(plan.read),
    )
