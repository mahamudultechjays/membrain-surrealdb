"""Scope endpoints: list the demo users and switch which of them the app acts as."""

from fastapi import APIRouter, Request

from app.api.deps import ActiveScopesDep, ScopeDirectoryDep, authorize_scopes
from app.schemas.scopes import (
    ScopeListResponse,
    ScopeOut,
    ScopeSwitchRequest,
    ScopeSwitchResponse,
)
from app.services import logger

router = APIRouter(prefix="/scopes")


@router.get("/list", response_model=ScopeListResponse)
async def list_scopes(directory: ScopeDirectoryDep, active: ActiveScopesDep) -> ScopeListResponse:
    """Every demo user, what each can read, and who is active now."""
    return ScopeListResponse(
        scopes=[
            ScopeOut(
                id=user.scope,
                name=user.name,
                type="user",
                team=user.team,
                reads=[layer.path for layer in directory.read_layers(user.scope)],
                has_own_key=directory.has_own_key(user.scope),
            )
            for user in directory.users()
        ],
        active_scopes=active.get(),
    )


@router.get("/active", response_model=ScopeSwitchResponse)
async def active_scopes(
    directory: ScopeDirectoryDep, active: ActiveScopesDep
) -> ScopeSwitchResponse:
    """Who the app is acting as now."""
    current = active.get()
    return ScopeSwitchResponse(
        active_scopes=current,
        previous_scopes=current,
        message=f"Acting as {directory.describe(current)}",
    )


@router.post("/switch", response_model=ScopeSwitchResponse)
async def switch_scopes(
    body: ScopeSwitchRequest,
    request: Request,
    directory: ScopeDirectoryDep,
    active: ActiveScopesDep,
) -> ScopeSwitchResponse:
    """Act as these users from now on. /ask uses them when no scope is passed."""
    authorize_scopes(request, directory, body.scopes)
    previous = active.switch(body.scopes)
    current = active.get()
    message = f"Scope context switched ({directory.describe(current)})"
    logger.log(
        "[SCOPING]",
        trace_id=getattr(request.state, "trace_id", None),
        from_scopes=",".join(previous),
        to_scopes=",".join(current),
        message=repr(message),
    )
    return ScopeSwitchResponse(active_scopes=current, previous_scopes=previous, message=message)
