"""Brain endpoint: every entity memory holds, with its facts and relations,
filtered by the scope each fact was written to.

Agent Memory's listings take no scope filter, so this filters on the scope
every fact and relation carries. Admins may see every scope; everyone else only
the scopes their grants let them read, exactly as /ask does.
"""

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Request, status

from app.api.deps import AccessServiceDep, CurrentUserDep, MemoryBrainDep, is_admin
from app.domain.errors import MemoryNotConfiguredError, MemoryUnavailableError
from app.domain.ports.memory_brain import BrainSource
from app.schemas.brain import (
    BrainEntityOut,
    BrainFactOut,
    BrainRelationOut,
    BrainResponse,
    BrainSourceOut,
)
from app.services import brain, logger

router = APIRouter(prefix="/brain")


@router.get(
    "",
    response_model=BrainResponse,
    responses={status.HTTP_503_SERVICE_UNAVAILABLE: {"description": "Agent Memory failing"}},
)
async def list_brain(
    request: Request,
    user: CurrentUserDep,
    access: AccessServiceDep,
    memory: MemoryBrainDep,
    scope: Annotated[list[str] | None, Query()] = None,
    subscopes: bool = False,
) -> BrainResponse:
    """Entities, newest activity first, with the facts and relations in scope.

    `scope` (repeatable or comma-separated) narrows to some scopes; with
    `subscopes`, the paths below each one count too. Without `scope`, everything
    the caller may read is listed.
    """
    allowed = (
        None if is_admin(user.email) else {g.scope_path for g in await access.readable(user.email)}
    )
    wanted = {s.strip().strip("/") for s in _split(scope)} if scope else None
    if wanted and allowed is not None and (missing := wanted - allowed):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, f"Not readable: {', '.join(sorted(missing))}"
        )
    try:
        snapshot = await memory.snapshot()
    except MemoryNotConfiguredError as exc:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Agent Memory is not configured. Set AGENT_MEMORY_* in .env.",
        ) from exc
    except MemoryUnavailableError as exc:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, f"Agent Memory call failed: {exc}"
        ) from exc

    found = brain.view(snapshot, brain.ScopeFilter(allowed, wanted, subscopes=subscopes))
    entities = [_entity_out(e, found.names) for e in found.entities]
    response = BrainResponse(
        entities=entities,
        scopes=found.scopes,
        total_facts=sum(len(e.facts) for e in entities),
        total_relations=sum(len(e.relations) for e in entities),
    )
    logger.log(
        "[BRAIN]",
        trace_id=getattr(request.state, "trace_id", None),
        user=user.email,
        scopes=",".join(sorted(wanted)) if wanted else "all",
        entities=len(entities),
        facts=response.total_facts,
    )
    return response


def _entity_out(entity: brain.EntityView, names: dict[str, str]) -> BrainEntityOut:
    return BrainEntityOut(
        ref=entity.ref,
        name=entity.name,
        entity_type=entity.entity_type,
        category=entity.category,
        scopes=entity.scopes,
        updated_at=entity.updated_at,
        facts=[
            BrainFactOut(
                id=f.id,
                entity_ref=f.entity_ref,
                key=f.key,
                value=f.value,
                category=f.category,
                scopes=list(f.scopes),
                created_at=f.created_at,
                replaced=f.superseded_by is not None,
                summary=f.summary,
                labels=list(f.labels),
                confidence=f.confidence,
                importance=f.importance,
                supersedes=f.supersedes,
                superseded_by=f.superseded_by,
                valid_from=f.valid_from,
                valid_until=f.valid_until,
                source=_source_out(f.source),
            )
            for f in entity.facts
        ],
        relations=[
            BrainRelationOut(
                id=r.id,
                subject_ref=r.subject_ref,
                label=r.label,
                object_ref=r.object_ref,
                object_name=names.get(r.object_ref) or r.object_ref.partition("/")[2],
                category=r.category,
                scopes=list(r.scopes),
                created_at=r.created_at,
                summary=r.summary,
                labels=list(r.labels),
                confidence=r.confidence,
                valid_from=r.valid_from,
                valid_until=r.valid_until,
                source=_source_out(r.source),
            )
            for r in entity.relations
        ],
    )


def _source_out(source: BrainSource) -> BrainSourceOut:
    return BrainSourceOut(
        kind=source.kind, ref=source.ref, session_id=source.session_id, trust=source.trust
    )


def _split(values: list[str]) -> list[str]:
    return [part for value in values for part in value.split(",") if part.strip()]
