"""Ask in chat mode: an answer with citations, read only from the user's granted scopes.

The user's message is stored in their personal scope (Agent Memory's /chat
always stores the user turn).
"""

import time

from fastapi import APIRouter, HTTPException, Request, status

from app.api.deps import AccessServiceDep, ChatSessionsDep, CurrentUserDep, MemoryChatDep
from app.domain.errors import MemoryNotConfiguredError, MemoryUnavailableError, ScopeNotGrantedError
from app.schemas.chat import ChatCitationOut, ChatRequest, ChatResponse
from app.services import chat_flow, logger

router = APIRouter(prefix="/ask")


@router.post(
    "/chat",
    response_model=ChatResponse,
    responses={
        status.HTTP_403_FORBIDDEN: {"description": "A scope the user can't read"},
        status.HTTP_404_NOT_FOUND: {"description": "Not this user's chat session"},
        status.HTTP_503_SERVICE_UNAVAILABLE: {"description": "Agent Memory failing"},
    },
)
async def chat(
    body: ChatRequest,
    request: Request,
    user: CurrentUserDep,
    access: AccessServiceDep,
    memory: MemoryChatDep,
    sessions: ChatSessionsDep,
) -> ChatResponse:
    """Answer from every scope the signed-in user may read, citing sources inline."""
    try:
        plan = chat_flow.plan_access(
            user.email, await access.readable(user.email), wanted=body.scopes
        )
    except ScopeNotGrantedError as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, f"Not readable: {exc}") from exc
    if body.session_id and not sessions.belongs_to(body.session_id, user.email):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such chat session for this user.")

    started = time.perf_counter()
    try:
        reply = await memory.chat(body.message, access=plan, session_id=body.session_id)
    except MemoryNotConfiguredError as exc:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Agent Memory is not configured. Set AGENT_MEMORY_* in .env.",
        ) from exc
    except MemoryUnavailableError as exc:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, f"Agent Memory call failed: {exc}"
        ) from exc
    sessions.remember(reply.session_id, user.email)

    trace_id = getattr(request.state, "trace_id", None)
    logger.log(
        "[CHAT]",
        trace_id=trace_id,
        user=user.email,
        scopes=",".join(plan.read),
        stored_in=plan.write,
        session=reply.session_id,
        new_session=body.session_id is None,
        q=repr(body.message[:80]),
        citations=len(reply.citations),
        facts_saved=reply.facts_saved,
        latency_ms=round((time.perf_counter() - started) * 1000),
        memory_trace=reply.trace_id,
    )
    return ChatResponse(
        reply=reply.reply,
        session_id=reply.session_id,
        scopes=list(plan.read),
        citations=[
            ChatCitationOut(
                marker=c.marker,
                id=c.id,
                kind=c.kind,
                snippet=c.snippet,
                score=round(c.score, 3),
                document_title=c.document_title,
                position_percent=c.position_percent,
                role=c.role,
                occurred_at=c.occurred_at,
            )
            for c in reply.citations
        ],
        facts_saved=reply.facts_saved,
        trace_id=reply.trace_id,
    )
