"""Admin endpoints: assign and revoke users' scope grants, list and register scopes.

This is the governance layer the backend owns: Agent Memory is reached with one
admin key, so who may read or write which scope lives here. Only emails in
ADMIN_EMAILS get past `require_admin`. Scopes are kept under ORG_SCOPE.
"""

from collections import defaultdict

from fastapi import APIRouter, HTTPException, Request, status

from app.api.deps import (
    AccessServiceDep,
    AdminUserDep,
    MemoryPeopleDep,
    OnboardingServiceDep,
    ScopeRegistryDep,
    is_admin,
)
from app.api.v1.endpoints.onboarding import status_of
from app.core.config import settings
from app.domain.errors import (
    MemoryNotConfiguredError,
    MemoryUnavailableError,
    UnknownVctNodeError,
)
from app.domain.ports.user_scopes import ScopeGrant
from app.schemas.admin import (
    GrantRequest,
    RegisterScopeRequest,
    ScopesResponse,
    UserGrants,
    UsersResponse,
)
from app.schemas.auth import GrantOut
from app.schemas.onboarding import AdminVctRequest, OnboardingStatus, SeedResponse
from app.services import logger

router = APIRouter(prefix="/admin")


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
    request: Request, admin: AdminUserDep, onboarding: OnboardingServiceDep, force: bool = False
) -> SeedResponse:
    """Store the VCT nodes in the matcher scope, once. `seeded: 0` means it was
    already there; `force` writes them again (duplicates are harmless)."""
    try:
        seeded = await onboarding.seed(force=force)
    except (MemoryNotConfiguredError, MemoryUnavailableError) as exc:
        raise _unavailable(exc) from exc
    _log(request, admin.email, "vct_seed", None, settings.VCT_SCOPE, str(seeded))
    return SeedResponse(scope=settings.VCT_SCOPE, seeded=seeded)


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
