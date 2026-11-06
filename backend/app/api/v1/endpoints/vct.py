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
from app.domain.ports.fact_tags import FactTagRepository
from app.domain.vct import VctMap
from app.schemas.vct_tags import (
    CoverageCell,
    CoverageCount,
    FactTagDetail,
    TagEditRequest,
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
    """Change, remove or accept a fact's node or goal. A person's tag is never
    replaced by the tagger."""
    fid, scope = await _readable(fact_id, user.email, access, tags)
    try:
        if body.action == "change":
            tag = (body.tag or "").strip()
            known = vmap.node(tag) if body.kind == "node" else vmap.goal(tag)
            if known is None:
                raise HTTPException(
                    status.HTTP_422_UNPROCESSABLE_CONTENT,
                    f"Unknown VCT {body.kind}: {tag or '(none)'}",
                )
            await tags.set_tag(fid, body.kind, tag, user.email)
        elif body.action == "remove":
            await tags.remove(fid, body.kind, user.email)
        else:
            await tags.accept(fid, body.kind, user.email)
    except FactNotTaggedError as exc:  # removed between the check and the edit
        raise _not_tagged() from exc
    logger.log(
        "[TAG]",
        trace_id=getattr(request.state, "trace_id", None),
        user=user.email,
        fact=fid,
        scope=scope,
        kind=body.kind,
        action=body.action,
        value=body.tag,
    )
    return await _detail(fid, scope, tags, vmap)


@router.get("/vct/coverage", response_model=VctCoverage)
async def coverage(
    user: CurrentUserDep,
    access: AccessServiceDep,
    tags: FactTagRepositoryDep,
    vmap: VctMapDep,
) -> VctCoverage:
    """How many facts carry each node and goal, and a domain x section grid,
    over the scopes the caller may read. A cell with nodes but no facts is a gap."""
    scopes = sorted({g.scope_path for g in await access.readable(user.email)})
    counts = await tags.counts(scopes)
    tagged, without_goal = await tags.totals(scopes)
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
    return FactTagDetail(
        fact_id=fid,
        scope=scope,
        nodes=[r for r in refs if r.kind == "node"],
        goals=[r for r in refs if r.kind == "goal"],
    )


def _not_tagged() -> HTTPException:
    return HTTPException(status.HTTP_404_NOT_FOUND, "This fact has not been tagged yet.")
