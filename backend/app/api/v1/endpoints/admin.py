"""Admin endpoints: assign and revoke users' scope grants, list and register scopes.

This is the governance layer the backend owns: Agent Memory is reached with one
admin key, so who may read or write which scope lives here. Only emails in
ADMIN_EMAILS get past `require_admin`. Scopes are kept under ORG_SCOPE.
"""

from collections import defaultdict
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, HTTPException, Request, status

from app.api.deps import (
    AccessServiceDep,
    AdminUserDep,
    FactTagRepositoryDep,
    MemoryPeopleDep,
    OnboardingServiceDep,
    ScopeRegistryDep,
    TaggerServiceDep,
    is_admin,
)
from app.api.v1.endpoints.onboarding import status_of
from app.core.config import settings
from app.domain.errors import (
    MemoryNotConfiguredError,
    MemoryUnavailableError,
    TeamScopeWriteError,
    UnknownVctNodeError,
)
from app.domain.ports.fact_tags import FactTagRepository
from app.domain.ports.user_scopes import ScopeGrant
from app.schemas.admin import (
    GrantRequest,
    RegisterScopeRequest,
    ScopesResponse,
    TeamAdminsResponse,
    UserGrants,
    UsersResponse,
)
from app.schemas.auth import GrantOut
from app.schemas.onboarding import AdminVctRequest, OnboardingStatus, SeedResponse
from app.schemas.tagger import ConfusionOut, TaggerRunOut, TaggerStats, TaggerStatus
from app.services import logger
from app.services.tagger import TaggerRun, TaggerService

router = APIRouter(prefix="/admin")

# The window for the tagger's correction rate.
STATS_DAYS = 7


@router.get("/users", response_model=UsersResponse)
async def list_users(
    admin: AdminUserDep, access: AccessServiceDep, people: MemoryPeopleDep
) -> UsersResponse:
    """Everyone who holds a grant here, then every other person Agent Memory knows.

    The second group has no scopes in this app yet: they get them through
    "Add scope", and their personal scope when they first sign in. Each person
    also carries their own grants in Agent Memory, read only: those apply when
    they reach Agent Memory directly (Claude Code, MCP), not through this app.
    """
    by_user: dict[str, list[ScopeGrant]] = defaultdict(list)
    for grant in await access.all_grants():
        by_user[grant.email].append(grant)
    owners = await access.owners()
    error: str | None = None
    try:
        known = {p.email: p for p in await people.list()}
    except MemoryNotConfiguredError:
        known, error = {}, "Agent Memory is not configured."
    except MemoryUnavailableError as exc:
        known, error = {}, f"Agent Memory call failed: {exc}"

    def memory_grants(email: str) -> dict[str, list[str]] | None:
        person = known.get(email.strip().lower())
        return person.grants if person else None

    users = [
        UserGrants(
            email=email,
            name=grants[0].name,
            is_admin=is_admin(email),
            grants=_grants_out(grants, owners),
            memory_grants=memory_grants(email),
        )
        for email, grants in by_user.items()
    ]
    others = [p for p in known.values() if p.email not in by_user]
    users += [
        UserGrants(
            email=p.email,
            name=p.name,
            is_admin=is_admin(p.email),
            grants=[],
            memory_grants=p.grants,
        )
        for p in sorted(others, key=lambda p: p.name.lower())
    ]
    return UsersResponse(users=users, people_error=error, memory_loaded=error is None)


@router.post(
    "/users/{email}/grants", response_model=UserGrants, status_code=status.HTTP_201_CREATED
)
async def add_grant(
    email: str,
    body: GrantRequest,
    request: Request,
    admin: AdminUserDep,
    access: AccessServiceDep,
) -> UserGrants:
    """Give a user read or write on a scope, registering the scope if it is new."""
    path = _under_org(body.scope_path)
    held = await access.grants_for(email)
    name = held[0].name if held else (body.name or email)
    try:
        await access.grant(email, name, path, body.access, body.layer)
    except TeamScopeWriteError as exc:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "The team scope is written only by promotion approval."
        ) from exc
    except (MemoryNotConfiguredError, MemoryUnavailableError) as exc:
        raise _unavailable(exc) from exc
    _log(request, admin.email, "grant", email, path, body.access)
    return await _user(access, email)


@router.delete("/users/{email}/grants", status_code=status.HTTP_204_NO_CONTENT)
async def remove_grant(
    email: str, scope_path: str, request: Request, admin: AdminUserDep, access: AccessServiceDep
) -> None:
    """Take a scope away from a user. The scope and its data stay in Agent Memory."""
    if not await access.revoke(email, scope_path):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "That user does not hold that scope.")
    _log(request, admin.email, "revoke", email, scope_path.strip("/"), None)


@router.get("/team-admins", response_model=TeamAdminsResponse)
async def list_team_admins(admin: AdminUserDep, access: AccessServiceDep) -> TeamAdminsResponse:
    """Who holds the team-admin role (they review Admin > Promotion)."""
    return TeamAdminsResponse(emails=await access.team_admins())


@router.put("/team-admins/{email}", status_code=status.HTTP_204_NO_CONTENT)
async def add_team_admin(
    email: str, request: Request, admin: AdminUserDep, access: AccessServiceDep
) -> None:
    await access.set_team_admin(email, True)
    _log(request, admin.email, "team_admin_on", email, settings.PROMOTION_TEAM_SCOPE, None)


@router.delete("/team-admins/{email}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_team_admin(
    email: str, request: Request, admin: AdminUserDep, access: AccessServiceDep
) -> None:
    await access.set_team_admin(email, False)
    _log(request, admin.email, "team_admin_off", email, settings.PROMOTION_TEAM_SCOPE, None)


@router.get("/scopes", response_model=ScopesResponse)
async def list_scopes(
    admin: AdminUserDep, registry: ScopeRegistryDep, prefix: str | None = None
) -> ScopesResponse:
    """Scopes registered in Agent Memory under ORG_SCOPE (or a narrower prefix)."""
    try:
        paths = await registry.list(_under_org(prefix or settings.ORG_SCOPE))
    except (MemoryNotConfiguredError, MemoryUnavailableError) as exc:
        raise _unavailable(exc) from exc
    return ScopesResponse(scopes=sorted(paths))


@router.post("/scopes", response_model=ScopesResponse, status_code=status.HTTP_201_CREATED)
async def register_scope(
    body: RegisterScopeRequest,
    request: Request,
    admin: AdminUserDep,
    registry: ScopeRegistryDep,
) -> ScopesResponse:
    """Register a new scope path (and any missing parent) in Agent Memory."""
    path = _under_org(body.path)
    try:
        await registry.ensure(path)
    except (MemoryNotConfiguredError, MemoryUnavailableError) as exc:
        raise _unavailable(exc) from exc
    _log(request, admin.email, "register", None, path, None)
    return ScopesResponse(scopes=[path])


@router.post("/vct/seed", response_model=SeedResponse)
async def seed_vct(
    request: Request,
    admin: AdminUserDep,
    onboarding: OnboardingServiceDep,
    tagger: TaggerServiceDep,
    force: bool = False,
    with_decoys: bool = False,
) -> SeedResponse:
    """Store the VCT nodes and goals in their matcher scopes, once. `seeded: 0`
    means they were already there; `force` writes them again (duplicates are harmless).
    The "not business" decoys go in with the nodes, or alone with `with_decoys`."""
    try:
        seeded = await onboarding.seed(force=force)
        goals = await tagger.seed_goals(force=force)
        # Decoys live beside the nodes; add them whenever the nodes are written.
        decoys = await tagger.seed_decoys() if seeded or force or with_decoys else 0
    except (MemoryNotConfiguredError, MemoryUnavailableError) as exc:
        raise _unavailable(exc) from exc
    _log(request, admin.email, "vct_seed", None, settings.VCT_SCOPE, f"{seeded}/{goals}")
    return SeedResponse(
        scope=settings.VCT_SCOPE,
        seeded=seeded,
        goals_scope=settings.VCT_GOALS_SCOPE,
        goals_seeded=goals,
        decoys_seeded=decoys,
    )


@router.get("/vct/tagger", response_model=TaggerStatus)
async def tagger_status(
    admin: AdminUserDep, tagger: TaggerServiceDep, tags: FactTagRepositoryDep
) -> TaggerStatus:
    """The VCT tagger: what it tags, whether it is running, its last run, and
    how often people corrected its tags in the last 7 days."""
    return await _tagger_status(tagger, tags)


@router.post("/vct/tagger/run", response_model=TaggerStatus, status_code=status.HTTP_202_ACCEPTED)
async def run_tagger(
    request: Request,
    admin: AdminUserDep,
    tagger: TaggerServiceDep,
    tags: FactTagRepositoryDep,
    retag: bool = False,
) -> TaggerStatus:
    """Start a tagger run now, in the background; 409 while one is running.
    `retag` re-tags every fact in the tagged scopes; a person's tags stay."""
    if not tagger.start(retag=retag):
        raise HTTPException(status.HTTP_409_CONFLICT, "The VCT tagger is already running.")
    action = "vct_tagger_retag" if retag else "vct_tagger_run"
    _log(request, admin.email, action, None, ",".join(tagger.scopes), None)
    return await _tagger_status(tagger, tags)


async def _tagger_status(tagger: TaggerService, tags: FactTagRepository) -> TaggerStatus:
    since = (datetime.now(UTC) - timedelta(days=STATS_DAYS)).isoformat(timespec="seconds")
    feedback = await tags.feedback_stats(since)
    tagged, _, not_business = await tags.totals(tagger.scopes)
    return TaggerStatus(
        enabled=settings.TAGGER_ENABLED,
        version=tagger.version,
        scopes=tagger.scopes,
        interval_hours=settings.TAGGER_INTERVAL_HOURS,
        running=tagger.running,
        next_run_at=tagger.next_run_at,
        current=_run_out(tagger.current),
        last=_run_out(tagger.last),
        tagged_facts=tagged,
        not_business=not_business,
        stats=TaggerStats(
            days=STATS_DAYS,
            edits=feedback.edits,
            corrections=feedback.corrections,
            correction_rate=round(feedback.corrections / feedback.edits, 3)
            if feedback.edits
            else None,
            confusions=[ConfusionOut(old=o, new=n, times=t) for o, n, t in feedback.confusions],
        ),
    )


def _run_out(run: TaggerRun | None) -> TaggerRunOut | None:
    if run is None:
        return None
    return TaggerRunOut(
        started_at=run.started_at,
        finished_at=run.finished_at,
        scopes=run.scopes,
        listed=run.listed,
        new=run.new,
        tagged=run.tagged,
        not_business=run.not_business,
        carried=run.carried,
        failed=run.failed,
        capped=run.capped,
        error=run.error,
    )


@router.get("/users/{email}/onboarding", response_model=OnboardingStatus)
async def user_onboarding(
    email: str, admin: AdminUserDep, onboarding: OnboardingServiceDep
) -> OnboardingStatus:
    """A user's description, confirmed VCT nodes and the domains they give."""
    return status_of(email, await onboarding.get(email), onboarding.map)


@router.put("/users/{email}/vct", response_model=OnboardingStatus)
async def set_user_vct(
    email: str,
    body: AdminVctRequest,
    request: Request,
    admin: AdminUserDep,
    onboarding: OnboardingServiceDep,
) -> OnboardingStatus:
    """Replace a user's VCT nodes (marked confirmed_by admin), keeping their answers."""
    current = await onboarding.get(email)
    try:
        record = await onboarding.confirm(
            email,
            primary_work=current.primary_work if current else "",
            node_ids=body.node_ids,
            primary_node_id=body.primary_node_id,
            role=current.role if current else None,
            team=current.team if current else None,
            by="admin",
        )
    except UnknownVctNodeError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    _log(request, admin.email, "vct_set", email, settings.VCT_SCOPE, ",".join(body.node_ids))
    return status_of(email, record, onboarding.map)


async def _user(access: AccessServiceDep, email: str) -> UserGrants:
    grants = await access.grants_for(email)
    return UserGrants(
        email=email.strip().lower(),
        name=grants[0].name if grants else email,
        is_admin=is_admin(email),
        grants=_grants_out(grants, await access.owners()),
    )


def _grants_out(grants: list[ScopeGrant], owners: dict[str, str]) -> list[GrantOut]:
    """The grants as returned, each with the name of whose space it is."""
    return [
        GrantOut.model_validate(g).model_copy(update={"owner": owners.get(g.scope_path)})
        for g in grants
    ]


def _under_org(path: str) -> str:
    """Keep admin changes inside the org tree, e.g. not at the Context root."""
    path = path.strip("/")
    org = settings.ORG_SCOPE.strip("/")
    if path != org and not path.startswith(f"{org}/"):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"Scopes must be under {org}.")
    return path


def _unavailable(exc: Exception) -> HTTPException:
    if isinstance(exc, MemoryNotConfiguredError):
        return HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Agent Memory is not configured.")
    return HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, f"Agent Memory call failed: {exc}")


def _log(
    request: Request,
    admin: str,
    action: str,
    user: str | None,
    scope: str,
    access: str | None,
) -> None:
    logger.log(
        "[ADMIN]",
        trace_id=getattr(request.state, "trace_id", None),
        admin=admin,
        action=action,
        user=user,
        scope=scope,
        access=access,
    )
