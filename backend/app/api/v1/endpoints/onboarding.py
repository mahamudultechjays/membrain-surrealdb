"""Onboarding endpoints: describe your work, confirm VCT nodes, get your domains.

Flow: POST /onboarding/preview suggests nodes per clause, the user ticks the
ones that fit, POST /onboarding/confirm saves them. Domains follow from the
nodes. Team scopes are not granted yet: the domain -> team mapping is pending.
"""

from fastapi import APIRouter, HTTPException, Request, status

from app.api.deps import CurrentUserDep, OnboardingServiceDep
from app.domain.errors import (
    MemoryNotConfiguredError,
    MemoryUnavailableError,
    UnknownVctNodeError,
    VctNotSeededError,
)
from app.domain.ports.onboarding import OnboardingRecord
from app.domain.vct import VctMap, VctNode
from app.schemas.onboarding import (
    ClauseOut,
    DomainRef,
    MappedNodeOut,
    OnboardingConfirmRequest,
    OnboardingPreviewRequest,
    OnboardingPreviewResponse,
    OnboardingStatus,
    VctDomainOut,
    VctGoalOut,
    VctMapResponse,
    VctNodeOut,
    VctSectionOut,
)
from app.services import logger

router = APIRouter()


@router.get("/vct/map", response_model=VctMapResponse)
async def vct_map(user: CurrentUserDep, onboarding: OnboardingServiceDep) -> VctMapResponse:
    """Every VCT node grouped by domain, and every goal grouped by section,
    for the node and goal pickers."""
    vmap = onboarding.map
    return VctMapResponse(
        topology_version=vmap.topology_version,
        domains=[
            VctDomainOut(
                id=d.id,
                name=d.name,
                # By each node's own domain_id: the map's domain lists put mkt1
                # under both marketing and product-innovation.
                nodes=[_node(n) for n in vmap.nodes if n.domain_id == d.id],
            )
            for d in vmap.domains
        ],
        sections=[
            VctSectionOut(
                id=sec.id,
                label=sec.label,
                ebitda_weight=sec.ebitda_weight,
                goals=[
                    VctGoalOut(id=g.id, name=g.name, description=g.description, weight=g.weight)
                    for g in vmap.goals
                    if g.section_id == sec.id
                ],
            )
            for sec in vmap.sections
        ],
    )


@router.get("/onboarding", response_model=OnboardingStatus)
async def get_onboarding(
    user: CurrentUserDep, onboarding: OnboardingServiceDep
) -> OnboardingStatus:
    """`onboarded: false` means show the onboarding screen."""
    return status_of(user.email, await onboarding.get(user.email), onboarding.map)


@router.post("/onboarding/preview", response_model=OnboardingPreviewResponse)
async def preview(
    body: OnboardingPreviewRequest,
    request: Request,
    user: CurrentUserDep,
    onboarding: OnboardingServiceDep,
) -> OnboardingPreviewResponse:
    """Suggest up to three nodes per clause of the description. Nothing is saved."""
    try:
        matches = await onboarding.suggest(body.primary_work)
    except VctNotSeededError as exc:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "The VCT map is not seeded in Agent Memory yet; an admin must run it once.",
        ) from exc
    except (MemoryNotConfiguredError, MemoryUnavailableError) as exc:
        raise unavailable(exc) from exc
    suggested = list(dict.fromkeys(m.candidates[0].id for m in matches if m.candidates))
    logger.log(
        "[ONBOARD]",
        trace_id=getattr(request.state, "trace_id", None),
        user=user.email,
        action="preview",
        clauses=len(matches),
        suggested=",".join(suggested),
    )
    return OnboardingPreviewResponse(
        clauses=[
            ClauseOut(clause=m.clause, candidates=[_node(n) for n in m.candidates]) for m in matches
        ],
        suggested=suggested,
        domains=[DomainRef(id=d.id, name=d.name) for d in onboarding.map.domains_of(suggested)],
    )


@router.post("/onboarding/confirm", response_model=OnboardingStatus)
async def confirm(
    body: OnboardingConfirmRequest,
    request: Request,
    user: CurrentUserDep,
    onboarding: OnboardingServiceDep,
) -> OnboardingStatus:
    """Save the chosen nodes (first is primary unless `primary_node_id` says
    otherwise). Calling it again replaces the earlier choice."""
    try:
        record = await onboarding.confirm(
            user.email,
            primary_work=body.primary_work,
            node_ids=body.node_ids,
            primary_node_id=body.primary_node_id,
            role=body.role,
            team=body.team,
        )
    except UnknownVctNodeError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    result = status_of(user.email, record, onboarding.map)
    logger.log(
        "[ONBOARD]",
        trace_id=getattr(request.state, "trace_id", None),
        user=user.email,
        action="confirm",
        nodes=",".join(n.id for n in result.nodes),
        domains=",".join(d.id for d in result.domains),
    )
    return result


def status_of(email: str, record: OnboardingRecord | None, vmap: VctMap) -> OnboardingStatus:
    if record is None:
        return OnboardingStatus(email=email.strip().lower(), onboarded=False)
    nodes = [
        MappedNodeOut(
            **_node(n).model_dump(),
            rank=m.rank,
            is_primary=m.is_primary,
            confirmed_by=m.confirmed_by,
        )
        for m in record.nodes
        if (n := vmap.node(m.node_id))
    ]
    ordered = sorted(nodes, key=lambda n: (not n.is_primary, n.rank))
    return OnboardingStatus(
        email=record.email,
        onboarded=True,
        primary_work=record.primary_work,
        role=record.role,
        team=record.team,
        onboarded_at=record.onboarded_at,
        nodes=nodes,
        domains=[DomainRef(id=d.id, name=d.name) for d in vmap.domains_of([n.id for n in ordered])],
    )


def unavailable(exc: Exception) -> HTTPException:
    if isinstance(exc, MemoryNotConfiguredError):
        return HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Agent Memory is not configured.")
    return HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, f"Agent Memory call failed: {exc}")


def _node(node: VctNode) -> VctNodeOut:
    return VctNodeOut(
        id=node.id,
        name=node.name,
        description=node.description,
        domain_id=node.domain_id,
        section_id=node.section_id,
    )
