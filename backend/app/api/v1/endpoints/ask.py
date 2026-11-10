"""Ask endpoint: what memory knows, grouped org -> team -> personal.

Reads only the scopes the signed-in user's grants allow, each through a lens.
`mode` picks how disagreements between scopes are handled (see
app.services.ask_modes). /ask/compare answers in Best match and By layer at
once, from one recall.
"""

from collections.abc import Awaitable
from datetime import UTC, datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, HTTPException, Query, Request, status

from app.api.deps import (
    AccessServiceDep,
    CurrentUserDep,
    FactProvenanceDep,
    MemoryRecallDep,
    is_admin,
)
from app.core.config import settings
from app.domain.errors import MemoryNotConfiguredError, MemoryUnavailableError
from app.domain.ports.fact_provenance import FactProvenance
from app.domain.ports.user_scopes import ScopeGrant
from app.schemas.ask import (
    AskCompareResponse,
    AskConflict,
    AskFact,
    AskLayer,
    AskMetadata,
    AskModeName,
    AskResponse,
    ConflictValueOut,
    FactProvenanceOut,
    FactSource,
)
from app.services import ask_flow, ask_modes, ask_provenance, logger

router = APIRouter(prefix="/ask")

_UNAVAILABLE: dict[int | str, dict[str, Any]] = {
    status.HTTP_503_SERVICE_UNAVAILABLE: {"description": "Agent Memory failing"}
}


@router.get("", response_model=AskResponse, responses=_UNAVAILABLE)
async def ask(
    request: Request,
    user: CurrentUserDep,
    access: AccessServiceDep,
    recall: MemoryRecallDep,
    provenance: FactProvenanceDep,
    q: Annotated[str, Query(min_length=1, max_length=1000)],
    scope: Annotated[list[str] | None, Query()] = None,
    as_user: Annotated[list[str] | None, Query()] = None,
    include_inferred: bool = False,
    mode: AskModeName | None = None,
) -> AskResponse:
    """Search every scope the signed-in user may read.

    `scope` (repeatable or comma-separated) narrows the search to some of those
    scopes. Admins may pass `as_user` emails to ask as other users, e.g. two
    people at once; their combined grants are read. `mode` is default,
    best_match or by_layer; without it, ASK_MODE_DEFAULT decides.
    """
    mode_used, mode_source = ask_modes.resolve_mode(mode, settings.ASK_MODE_DEFAULT)
    emails, grants, scopes = await _readable(user.email, access, scope, as_user)
    result = await _recalling(
        ask_modes.run(
            mode_used,
            recall,
            grants,
            q=q,
            tie_margin=settings.ASK_TIE_MARGIN,
            min_score=settings.ASK_CONFLICT_MIN_SCORE,
        )
    )
    trust = await _trust(provenance, result.answer)
    trace_id = getattr(request.state, "trace_id", None)
    _log(result, mode_source, trace_id, user.email, emails if as_user else None, scopes, q)
    return _response(result, mode_source, trace_id, q, scopes, include_inferred, trust)


@router.get("/compare", response_model=AskCompareResponse, responses=_UNAVAILABLE)
async def compare(
    request: Request,
    user: CurrentUserDep,
    access: AccessServiceDep,
    recall: MemoryRecallDep,
    provenance: FactProvenanceDep,
    q: Annotated[str, Query(min_length=1, max_length=1000)],
    scope: Annotated[list[str] | None, Query()] = None,
    as_user: Annotated[list[str] | None, Query()] = None,
    include_inferred: bool = False,
) -> AskCompareResponse:
    """Best match and By layer side by side, with the same parameters as /ask.

    Every scope is recalled once and both modes apply their rules to the same
    hits, so the two columns always describe the same facts. Each mode still
    logs its own [ASK] line, with mode_source "compare".
    """
    emails, grants, scopes = await _readable(user.email, access, scope, as_user)
    best, by_layer = await _recalling(
        ask_modes.compare(
            recall,
            grants,
            q=q,
            tie_margin=settings.ASK_TIE_MARGIN,
            min_score=settings.ASK_CONFLICT_MIN_SCORE,
        )
    )
    # Both modes share the recall, so one lookup serves both columns.
    trust = await _trust(provenance, best.answer)
    trace_id = getattr(request.state, "trace_id", None)
    for result in (best, by_layer):
        _log(result, "compare", trace_id, user.email, emails if as_user else None, scopes, q)
    return AskCompareResponse(
        q=q,
        best_match=_response(best, "compare", trace_id, q, scopes, include_inferred, trust),
        by_layer=_response(by_layer, "compare", trace_id, q, scopes, include_inferred, trust),
    )


async def _readable(
    email: str,
    access: AccessServiceDep,
    scope: list[str] | None,
    as_user: list[str] | None,
) -> tuple[list[str], list[ScopeGrant], list[str]]:
    """Whose grants are read, those grants (narrowed by `scope`), and their scope paths."""
    emails = [email]
    if as_user:
        if not is_admin(email):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Only admins can ask as other users.")
        emails = [e.lower() for e in _split(as_user)]
    grants = [g for e in emails for g in await access.readable(e)]
    if not grants:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No readable scopes for that user.")
    if scope:
        wanted = {s.strip("/") for s in _split(scope)}
        missing = wanted - {g.scope_path for g in grants}
        if missing:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN, f"Not readable: {', '.join(sorted(missing))}"
            )
        grants = [g for g in grants if g.scope_path in wanted]
    return emails, grants, list(dict.fromkeys(g.scope_path for g in grants))


async def _recalling[T](call: Awaitable[T]) -> T:
    """Agent Memory failures as 503s."""
    try:
        return await call
    except MemoryNotConfiguredError as exc:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Agent Memory is not configured. Set AGENT_MEMORY_* in .env.",
        ) from exc
    except MemoryUnavailableError as exc:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, f"Agent Memory call failed: {exc}"
        ) from exc


async def _trust(reader: FactProvenanceDep, answer: ask_flow.Answer) -> dict[str, FactProvenance]:
    return await ask_provenance.lookup(
        reader,
        answer,
        min_score=settings.ASK_CONFLICT_MIN_SCORE,
        max_entities=settings.ASK_PROVENANCE_MAX_ENTITIES,
    )


ModeSource = Literal["request", "config", "compare"]


def _log(
    result: ask_modes.ModeAnswer,
    mode_source: ModeSource,
    trace_id: str | None,
    user: str,
    as_users: list[str] | None,
    scopes: list[str],
    q: str,
) -> None:
    answer = result.answer
    logger.log(
        "[ASK]",
        trace_id=trace_id,
        mode=result.mode,
        mode_source=mode_source,
        conflicts=len(result.conflicts),
        user=user,
        as_users=",".join(as_users) if as_users else None,
        scopes=",".join(scopes),
        q=repr(q[:80]),
        facts_found=answer.total_facts,
        layers_failed=sum(1 for layer in answer.layers if layer.error) or None,
        latency_ms=answer.latency_ms,
        tier=",".join(answer.tiers) or None,
    )


def _response(
    result: ask_modes.ModeAnswer,
    mode_source: ModeSource,
    trace_id: str | None,
    q: str,
    scopes: list[str],
    include_inferred: bool,
    trust: dict[str, FactProvenance],
) -> AskResponse:
    answer = result.answer
    fact_conflict = {
        hit_id: conflict.id
        for conflict in result.conflicts
        for value in conflict.values
        for hit_id in value.hit_ids
    }
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
                            text=hit.text,
                            score=round(hit.score, 3),
                            occurred_at=hit.occurred_at,
                            provenance=_provenance_out(trust.get(hit.id)),
                        ),
                        status=verdict.status if (verdict := result.verdicts.get(hit.id)) else None,
                        reason=verdict.reason if verdict else None,
                        conflict_id=fact_conflict.get(hit.id),
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
            tie_margin=settings.ASK_TIE_MARGIN if result.mode == "best_match" else None,
        ),
        trace_id=trace_id,
        mode=result.mode,
        mode_source=mode_source,
        conflicts=[
            AskConflict(
                id=conflict.id,
                entity=conflict.entity,
                key=conflict.key,
                values=[
                    ConflictValueOut(
                        value=value.value,
                        layers=list(value.layers),
                        areas=value.areas,
                        hit_ids=value.hit_ids,
                        best_score=round(value.best_score, 3),
                    )
                    for value in conflict.values
                ],
                winner_hit_id=conflict.winner_hit_id,
                reason=conflict.reason,
            )
            for conflict in result.conflicts
        ],
    )


def _provenance_out(found: FactProvenance | None) -> FactProvenanceOut | None:
    if found is None:
        return None
    return FactProvenanceOut(
        trust=found.trust,
        confidence=found.confidence,
        source_kind=found.source_kind,
        created_at=found.created_at,
        valid_from=found.valid_from,
        valid_until=found.valid_until,
        superseded_by=found.superseded_by,
    )


def _split(scopes: list[str]) -> list[str]:
    """['a,b', 'c'] -> ['a', 'b', 'c'], keeping order and dropping repeats."""
    out: list[str] = []
    for part in (p.strip() for value in scopes for p in value.split(",")):
        if part and part not in out:
            out.append(part)
    return out
