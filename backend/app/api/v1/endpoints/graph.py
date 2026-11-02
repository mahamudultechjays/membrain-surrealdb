"""Graph endpoints: find an entity, then explore one hop at a time."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.deps import MemoryGraphDep, require_admin
from app.domain.errors import EntityNotFoundError, MemoryNotConfiguredError, MemoryUnavailableError
from app.schemas.graph import NeighbourhoodResponse, NodeOut, SearchResponse

# Admin-only: Agent Memory's entity and document reads take no lens, so with the
# one admin key they would show every scope. Users read through /ask instead.
router = APIRouter(prefix="/graph", dependencies=[Depends(require_admin)])


@router.get("/search", response_model=SearchResponse)
async def search(
    graph: MemoryGraphDep,
    q: Annotated[str, Query(min_length=1, max_length=200)],
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
) -> SearchResponse:
    """Entities whose names match `q`."""
    try:
        nodes = await graph.search(q, limit)
    except (MemoryNotConfiguredError, MemoryUnavailableError) as exc:
        raise _unavailable(exc) from exc
    return SearchResponse(entities=[NodeOut.model_validate(n) for n in nodes])


# `name:path` because entity names can contain "/".
@router.get("/entities/{entity_type}/{name:path}", response_model=NeighbourhoodResponse)
async def neighbourhood(
    entity_type: str,
    name: str,
    graph: MemoryGraphDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 40,
) -> NeighbourhoodResponse:
    """One entity, its facts, and its relations one hop out."""
    try:
        found = await graph.neighbourhood(entity_type, name, limit)
    except EntityNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Entity not found.") from exc
    except (MemoryNotConfiguredError, MemoryUnavailableError) as exc:
        raise _unavailable(exc) from exc
    return NeighbourhoodResponse.model_validate(found)


def _unavailable(exc: Exception) -> HTTPException:
    if isinstance(exc, MemoryNotConfiguredError):
        detail = "Agent Memory is not configured. Set AGENT_MEMORY_* in .env."
    else:
        detail = f"Agent Memory call failed: {exc}"
    return HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail)
