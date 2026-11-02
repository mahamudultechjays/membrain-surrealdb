"""Ask endpoint: what memory knows, grouped org -> team -> personal."""

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Request, status

from app.api.deps import (
    ActiveScopesDep,
    RecallFactoryDep,
    ScopeDirectoryDep,
    authorize_scopes,
)
from app.domain.errors import MemoryNotConfiguredError, MemoryUnavailableError
from app.schemas.ask import AskFact, AskLayer, AskMetadata, AskResponse, FactSource
from app.services import ask_flow, logger

router = APIRouter(prefix="/ask")


@router.get(
    "",
    response_model=AskResponse,
    responses={status.HTTP_503_SERVICE_UNAVAILABLE: {"description": "Agent Memory failing"}},
)
async def ask(
    request: Request,
    directory: ScopeDirectoryDep,
    recalls: RecallFactoryDep,
    active: ActiveScopesDep,
    q: Annotated[str, Query(min_length=1, max_length=1000)],
    scope: Annotated[list[str] | None, Query()] = None,
    include_inferred: bool = False,
) -> AskResponse:
    """Search every layer the scopes can read. Repeat `scope` (or comma-separate it)
    to ask as several users at once, e.g. Priya + Deena. Without `scope`, asks as
    the active scopes set by POST /scopes/switch."""
    scopes = _split(scope or []) or active.get()
    authorize_scopes(request, directory, scopes)
    try:
        answer = await ask_flow.ask(recalls, directory, q=q, scopes=scopes)
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
    logger.log(
        "[ASK]",
        trace_id=trace_id,
        scopes=",".join(scopes),
        q=repr(q[:80]),
        facts_found=answer.total_facts,
        layers_failed=sum(1 for layer in answer.layers if layer.error) or None,
        latency_ms=answer.latency_ms,
        tier=",".join(answer.tiers) or None,
    )
    return AskResponse(
        q=q,
        scopes=scopes,
        answered_at=datetime.now(UTC).isoformat(timespec="seconds"),
        layers=[
            AskLayer(
                layer=layer.layer,
                area=layer.area,
                owner=layer.owner,
                error=layer.error,
                facts=[
                    AskFact(
                        fact=hit.text,
                        source=FactSource(
                            kind=ask_flow.source_kind(hit),
                            hit_kind=hit.kind,
                            hit_id=hit.id,
                            quote=hit.text,
                            trust=round(hit.score, 3),
                        ),
                    )
                    for hit in layer.hits
                ],
            )
            for layer in answer.layers
        ],
        metadata=AskMetadata(
            total_facts=answer.total_facts,
            resolution_tier=",".join(answer.tiers) or None,
            latency_ms=answer.latency_ms,
            include_inferred=include_inferred,
            trace_ids=answer.trace_ids,
        ),
        trace_id=trace_id,
    )


def _split(scopes: list[str]) -> list[str]:
    """['a,b', 'c'] -> ['a', 'b', 'c'], keeping order and dropping repeats."""
    out: list[str] = []
    for part in (p.strip() for value in scopes for p in value.split(",")):
        if part and part not in out:
            out.append(part)
    return out
