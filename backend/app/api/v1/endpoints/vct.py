"""VCT tag endpoints: read and fix a fact's tags, and coverage over the map.

Tags live in our database as fact id + tags; the facts stay in Agent Memory.
Anyone who can read a fact's scope may fix its tags, and the fix applies for
everyone who reads that scope. Every edit is logged for tagger feedback.
"""

from collections import Counter

from fastapi import APIRouter, HTTPException, Request, status

from app.api.deps import (
    AccessServiceDep,
    CurrentUserDep,
    FactTagRepositoryDep,
    VctMapDep,
    is_admin,
)
from app.domain.errors import FactNotTaggedError
from app.domain.ports.fact_tags import FactTag, FactTagRepository, TagKind
from app.domain.vct import VctMap
from app.schemas.vct_tags import (
    CoverageCell,
    CoverageCount,
    FactTagDetail,
    ReviewBulkRequest,
    ReviewBulkResponse,
    TagEditRequest,
    TagRef,
    VctCoverage,
    tag_ref,
)
from app.services import logger
from app.services.access import AccessService
from app.services.vct_tags import FACT_PREFIX

router = APIRouter()


@router.get("/facts/{fact_id}/tags", response_model=FactTagDetail)
async def fact_tags(
    fact_id: str,
    user: CurrentUserDep,
    access: AccessServiceDep,
    tags: FactTagRepositoryDep,
    vmap: VctMapDep,
) -> FactTagDetail:
    """A fact's node and goal tags in rank order: the first is active, the rest
    are the tagger's alternatives for the editor."""
    fid, scope = await _readable(fact_id, user.email, access, tags)
    return await _detail(fid, scope, tags, vmap)


@router.put("/facts/{fact_id}/tags", response_model=FactTagDetail)
async def edit_fact_tags(
    fact_id: str,
    body: TagEditRequest,
    request: Request,
    user: CurrentUserDep,
    access: AccessServiceDep,
    tags: FactTagRepositoryDep,
    vmap: VctMapDep,
) -> FactTagDetail:
    """Change, remove or accept a fact's node or goal, or review it. A person's
    tag is never replaced by the tagger; any action marks the fact reviewed."""
    fid, scope = await _readable(fact_id, user.email, access, tags)
    kind = body.kind
    if body.action in ("change", "remove", "accept") and kind is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"{body.action} needs a kind.")
    try:
        if body.action == "change" and kind is not None:
            tag = (body.tag or "").strip()
            known = vmap.node(tag) if kind == "node" else vmap.goal(tag)
            if known is None:
                raise HTTPException(
                    status.HTTP_422_UNPROCESSABLE_CONTENT,
                    f"Unknown VCT {kind}: {tag or '(none)'}",
                )
            await tags.set_tag(fid, kind, tag, user.email)
        elif body.action == "remove" and kind is not None:
            await tags.remove(fid, kind, user.email)
        elif body.action == "accept" and kind is not None:
            await tags.accept(fid, kind, user.email)
        elif body.action == "confirm":
            await tags.confirm(fid, user.email)
        elif body.action == "not_business":
            await tags.mark_not_business(fid, user.email)
        elif body.action == "keep":
            await tags.keep(fid, user.email)
        else:
            guesses = await tags.guesses(fid)
            if not guesses:
                raise HTTPException(
                    status.HTTP_409_CONFLICT, "No guesses to use; pick a node or goal instead."
                )
            for guess_kind, ids in guesses.items():
                await tags.set_tag(fid, guess_kind, ids[0], user.email)
    except FactNotTaggedError as exc:  # removed between the check and the edit
        raise _not_tagged() from exc
    logger.log(
        "[TAG]",
        trace_id=getattr(request.state, "trace_id", None),
        user=user.email,
        fact=fid,
        scope=scope,
        kind=kind,
        action=body.action,
        value=body.tag,
    )
    return await _detail(fid, scope, tags, vmap)


@router.post("/facts/review", response_model=ReviewBulkResponse)
async def review_facts(
    body: ReviewBulkRequest,
    request: Request,
    user: CurrentUserDep,
    access: AccessServiceDep,
    tags: FactTagRepositoryDep,
) -> ReviewBulkResponse:
    """Review many facts at once ("Confirm all" on a group, or keep them).
    Facts the caller can't read, or not tagged yet, are skipped."""
    readable = {g.scope_path for g in await access.readable(user.email)}
    done: list[str] = []
    skipped: list[str] = []
    for raw in dict.fromkeys(body.fact_ids):
        fid = raw.removeprefix(FACT_PREFIX)
        scope = await tags.scope_of(fid)
        if scope is None or not (is_admin(user.email) or scope in readable):
            skipped.append(fid)
            continue
        try:
            if body.action == "confirm":
                await tags.confirm(fid, user.email)
            else:
                await tags.keep(fid, user.email)
        except FactNotTaggedError:
            skipped.append(fid)
            continue
        done.append(fid)
    logger.log(
        "[TAG]",
        trace_id=getattr(request.state, "trace_id", None),
        user=user.email,
        action=f"bulk_{body.action}",
        facts=str(len(done)),
        skipped=str(len(skipped)) if skipped else None,
    )
    return ReviewBulkResponse(done=done, skipped=skipped)


@router.get("/vct/coverage", response_model=VctCoverage)
async def coverage(
    user: CurrentUserDep,
    access: AccessServiceDep,
    tags: FactTagRepositoryDep,
    vmap: VctMapDep,
) -> VctCoverage:
    """How many facts carry each node and goal, and a domain x section grid,
    over the scopes the caller may read. A cell with nodes but no facts is a gap.
    Facts marked not business are counted apart and never in the grid."""
    scopes = sorted({g.scope_path for g in await access.readable(user.email)})
    counts = await tags.counts(scopes)
    tagged, without_goal, not_business = await tags.totals(scopes)
    by_node = {c.tag: c.facts for c in counts if c.kind == "node"}
    nodes_in: Counter[tuple[str, str]] = Counter()
    facts_in: Counter[tuple[str, str]] = Counter()
    for node in vmap.nodes:
        cell = (node.domain_id, node.section_id)
        nodes_in[cell] += 1
        facts_in[cell] += by_node.get(node.id, 0)
    return VctCoverage(
        scopes=scopes,
        tagged_facts=tagged,
        without_goal=without_goal,
        not_business=not_business,
        nodes=[CoverageCount(id=c.tag, facts=c.facts) for c in counts if c.kind == "node"],
        goals=[CoverageCount(id=c.tag, facts=c.facts) for c in counts if c.kind == "goal"],
        cells=[
            CoverageCell(domain_id=d, section_id=s, nodes=n, facts=facts_in[(d, s)])
            for (d, s), n in sorted(nodes_in.items())
        ],
    )


async def _readable(
    fact_id: str, email: str, access: AccessService, tags: FactTagRepository
) -> tuple[str, str]:
    """The stored fact id and its scope, if the caller may read that scope."""
    fid = fact_id.removeprefix(FACT_PREFIX)
    scope = await tags.scope_of(fid)
    if scope is None:
        raise _not_tagged()
    if not is_admin(email) and scope not in {g.scope_path for g in await access.readable(email)}:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You can't read this fact's scope.")
    return fid, scope


async def _detail(fid: str, scope: str, tags: FactTagRepository, vmap: VctMap) -> FactTagDetail:
    rows = (await tags.tags_for([fid])).get(fid, [])
    refs = [ref for row in rows if (ref := tag_ref(row, vmap))]
    state = (await tags.review_state([fid])).get(fid)
    guesses = await tags.guesses(fid)

    def guessed(kind: TagKind) -> list[TagRef]:
        made = (
            tag_ref(FactTag(fid, scope, kind, tag, rank, "auto", None, "tagger", ""), vmap)
            for rank, tag in enumerate(guesses.get(kind, []), start=1)
        )
        return [r for r in made if r]

    return FactTagDetail(
        fact_id=fid,
        scope=scope,
        business=fid not in await tags.not_business([fid]),
        tagged_at=state.tagged_at if state else None,
        reviewed_at=state.reviewed_at if state else None,
        reviewed_by=state.reviewed_by if state else None,
        guess_nodes=guessed("node"),
        guess_goals=guessed("goal"),
        nodes=[r for r in refs if r.kind == "node"],
        goals=[r for r in refs if r.kind == "goal"],
    )


def _not_tagged() -> HTTPException:
    return HTTPException(status.HTTP_404_NOT_FOUND, "This fact has not been tagged yet.")
