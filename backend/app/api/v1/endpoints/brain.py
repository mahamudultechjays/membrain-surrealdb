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
from app.domain.ports.memory_brain import BrainReplaced, BrainSource, BrainTurns
from app.schemas.brain import (
    BrainActionOut,
    BrainChunkOut,
    BrainEntityOut,
    BrainFactOut,
    BrainRelationOut,
    BrainResponse,
    BrainSourceOut,
    BrainUnknownOut,
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
    chunks: bool = True,
    replaced: bool = False,
) -> BrainResponse:
    """Entities, newest activity first, with the facts and relations in scope,
    the memory chunks (captured turns) they were extracted from, the actions
    memory recorded and what it could not settle.

    `scope` (repeatable or comma-separated) narrows to some scopes; with
    `subscopes`, the paths below each one count too. Without `scope`, everything
    the caller may read is listed. `chunks=false` skips reading the turns.
    `replaced=true` also reads each entity's history for the facts newer values
    replaced, which Agent Memory's fact listing leaves out.
    """
    allowed = (
        None if is_admin(user.email) else {g.scope_path for g in await access.readable(user.email)}
    )
    wanted = {s.strip().strip("/") for s in _split(scope)} if scope else None
    if wanted and allowed is not None and (missing := wanted - allowed):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, f"Not readable: {', '.join(sorted(missing))}"
        )
    scope_filter = brain.ScopeFilter(allowed, wanted, subscopes=subscopes)
    try:
        snapshot = await memory.snapshot()
        turns = (
            await memory.turns(brain.sessions(snapshot, scope_filter)) if chunks else BrainTurns()
        )
        old = (
            await memory.replaced(brain.entities_in(snapshot, scope_filter))
            if replaced
            else BrainReplaced()
        )
        snapshot = brain.with_replaced(snapshot, old.facts)
    except MemoryNotConfiguredError as exc:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Agent Memory is not configured. Set AGENT_MEMORY_* in .env.",
        ) from exc
    except MemoryUnavailableError as exc:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, f"Agent Memory call failed: {exc}"
        ) from exc

    found = brain.view(snapshot, scope_filter)
    entities = [_entity_out(e, found.names) for e in found.entities]
    chunk_views = brain.chunks(snapshot, turns.turns, scope_filter)
    response = BrainResponse(
        entities=entities,
        scopes=found.scopes,
        total_facts=sum(len(e.facts) for e in entities),
        total_relations=sum(len(e.relations) for e in entities),
        chunks=[
            BrainChunkOut(
                id=c.id,
                session_id=c.session_id,
                role=c.role,
                text=c.text,
                created_at=c.created_at,
                scopes=c.scopes,
                derived=c.derived,
            )
            for c in chunk_views
        ],
        total_chunks=len(chunk_views),
        chunks_missing=turns.missing,
        actions=[
            BrainActionOut(
                id=a.action.id,
                actor_ref=a.action.actor_ref,
                actor_name=a.actor_name,
                verb=a.action.verb,
                object_ref=a.action.object_ref,
                object_name=a.object_name,
                summary=a.action.summary,
                category=a.action.category,
                created_at=a.action.created_at,
                occurred_at=a.action.occurred_at,
                confidence=a.action.confidence,
                scopes=a.scopes,
                source=_source_out(a.action.source),
            )
            for a in brain.actions(snapshot, scope_filter, found.names)
        ],
        unknowns=[
            BrainUnknownOut(
                id=u.id,
                about=u.about,
                reason=u.reason,
                resolved=u.resolved,
                resolvable=u.resolvable,
                entity_ref=u.entity_ref,
                entity_name=found.names.get(u.entity_ref) if u.entity_ref else None,
                key=u.key,
                scopes=[p for p in u.scopes if scope_filter.visible(p)],
                labels=list(u.labels),
                created_at=u.created_at,
            )
            for u in brain.unknowns(snapshot, scope_filter)
        ],
        replaced_loaded=replaced,
        replaced_missing=old.missing,
    )
    logger.log(
        "[BRAIN]",
        trace_id=getattr(request.state, "trace_id", None),
        user=user.email,
        scopes=",".join(sorted(wanted)) if wanted else "all",
        entities=len(entities),
        facts=response.total_facts,
        chunks=response.total_chunks,
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
