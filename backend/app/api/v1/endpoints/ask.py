"""Ask endpoint: what memory knows, as one recall ranked by Agent Memory.

Reads only the scopes the signed-in user's grants allow, through one lens each.
With a VCT filter the same recall also yields the value-driven list.
"""

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Request, status

from app.api.deps import (
    AccessServiceDep,
    CurrentUserDep,
    FactTagRepositoryDep,
    MemoryRecallDep,
    VctMapDep,
    is_admin,
)
from app.domain.errors import MemoryNotConfiguredError, MemoryUnavailableError
from app.domain.ports.memory_recall import RecallHit
from app.domain.vct import VctMap
from app.schemas.ask import AskFact, AskFilter, AskMetadata, AskResponse, FactSource
from app.schemas.vct_tags import fact_tags_out
from app.services import ask_flow, logger
from app.services.vct_tags import HitTags, TagFilter, tag_answer

router = APIRouter(prefix="/ask")


@router.get(
    "",
    response_model=AskResponse,
    responses={status.HTTP_503_SERVICE_UNAVAILABLE: {"description": "Agent Memory failing"}},
)
async def ask(
    request: Request,
    user: CurrentUserDep,
    access: AccessServiceDep,
    recall: MemoryRecallDep,
    tag_store: FactTagRepositoryDep,
    vmap: VctMapDep,
    q: Annotated[str, Query(min_length=1, max_length=1000)],
    scope: Annotated[list[str] | None, Query()] = None,
    as_user: Annotated[list[str] | None, Query()] = None,
    goal: Annotated[list[str] | None, Query()] = None,
    node: Annotated[list[str] | None, Query()] = None,
    domain: Annotated[list[str] | None, Query()] = None,
    include_inferred: bool = False,
) -> AskResponse:
    """Search every scope the signed-in user may read.

    `scope` (repeatable or comma-separated) narrows the search to some of those
    scopes. Admins may pass `as_user` emails to ask as other users, e.g. two
    people at once; their combined grants are read.

    `goal`, `node` and `domain` (VCT ids, repeatable or comma-separated) fill
    `value_facts`: the hits whose active tag matches, any value within one kind
    and every kind given. `facts` always holds every hit.
    """
    flt = TagFilter(
        goals=frozenset(_split(goal or [])),
        nodes=frozenset(_split(node or [])),
        domains=frozenset(_split(domain or [])),
    )
    if unknown := flt.unknown(vmap):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, f"Unknown VCT ids: {', '.join(unknown)}"
        )
    emails = [user.email]
    if as_user:
        if not is_admin(user.email):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Only admins can ask as other users.")
        emails = [e.lower() for e in _split(as_user)]
    grants = [g for email in emails for g in await access.readable(email)]
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
    try:
        answer = await ask_flow.ask(recall, grants, q=q)
    except MemoryNotConfiguredError as exc:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Agent Memory is not configured. Set AGENT_MEMORY_* in .env.",
        ) from exc
    except MemoryUnavailableError as exc:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, f"Agent Memory call failed: {exc}"
        ) from exc

    tagged = await tag_answer(answer, tag_store, vmap, flt)

    def fact_out(hit: RecallHit) -> AskFact:
        return _fact(hit, tagged.tags.get(hit.id), vmap)

    trace_id = getattr(request.state, "trace_id", None)
    logger.log(
        "[ASK]",
        trace_id=trace_id,
        user=user.email,
        as_users=",".join(emails) if as_user else None,
        scopes=",".join(answer.scopes),
        q=repr(q[:80]),
        facts_found=len(answer.hits),
        latency_ms=answer.latency_ms,
        tier=answer.tier,
        vct_filter=",".join(sorted(flt.goals | flt.nodes | flt.domains)) or None,
        value_facts=len(tagged.kept) if tagged.kept is not None else None,
    )
    return AskResponse(
        q=q,
        scopes=answer.scopes,
        answered_at=datetime.now(UTC).isoformat(timespec="seconds"),
        facts=[fact_out(hit) for hit in answer.hits],
        value_facts=[fact_out(hit) for hit in tagged.kept] if tagged.kept is not None else None,
        metadata=AskMetadata(
            total_facts=len(answer.hits),
            resolution_tier=answer.tier,
            latency_ms=answer.latency_ms,
            include_inferred=include_inferred,
            trace_ids=[answer.trace_id] if answer.trace_id else [],
            filter=AskFilter(
                goals=sorted(flt.goals),
                nodes=sorted(flt.nodes),
                domains=sorted(flt.domains),
                removed=tagged.removed_total,
            )
            if flt.active
            else None,
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


def _fact(hit: RecallHit, tags: HitTags | None, vmap: VctMap) -> AskFact:
    return AskFact(
        fact=hit.text,
        source=FactSource(
            kind=ask_flow.source_kind(hit),
            hit_kind=hit.kind,
            hit_id=hit.id,
            text=hit.text,
            score=round(hit.score, 3),
        ),
        tags=fact_tags_out(tags, vmap),
    )
