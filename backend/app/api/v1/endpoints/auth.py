"""Auth endpoints: Entra ID SSO through the backend, as in membrain, plus a dev login.

The callback lands on <FRONTEND_URL>/api/v1/auth/callback (the frontend proxies
/api), exchanges the code, turns the claims into our user, creates their default
scopes on first sign-in, and stores {email, name} in the signed session cookie.
Every other endpoint reads the user from that cookie.
"""

import logging
from typing import Annotated, Any

from authlib.integrations.base_client import MismatchingStateError
from authlib.integrations.starlette_client import OAuthError
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse

from app.api.deps import AccessServiceDep, CurrentUserDep, is_admin
from app.core.config import settings
from app.core.oauth import get_oauth_client
from app.domain.errors import MemoryNotConfiguredError, MemoryUnavailableError
from app.schemas.auth import (
    AuthConfigResponse,
    CurrentUser,
    DevLoginRequest,
    GrantOut,
    MeResponse,
)
from app.services import logger as trace
from app.services.access import AccessService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth")

OAuthClientDep = Annotated[Any | None, Depends(get_oauth_client)]


@router.get("/config", response_model=AuthConfigResponse)
async def auth_config() -> AuthConfigResponse:
    """Which login the frontend should offer."""
    return AuthConfigResponse(
        sso_enabled=settings.sso_configured, dev_login_enabled=settings.dev_login_enabled
    )


@router.get("/login")
async def login(request: Request, oauth: OAuthClientDep) -> RedirectResponse:
    """Start SSO: redirect the browser to Microsoft Entra ID."""
    if oauth is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "SSO is not configured.")
    redirect: RedirectResponse = await oauth.authorize_redirect(
        request, settings.azure_redirect_uri
    )
    return redirect


@router.get("/callback")
async def callback(
    request: Request, oauth: OAuthClientDep, access: AccessServiceDep
) -> RedirectResponse:
    """Finish SSO: exchange the code, create default scopes once, set the session."""
    if oauth is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "SSO is not configured.")
    try:
        token = await oauth.authorize_access_token(request)
    except MismatchingStateError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid OAuth state") from exc
    except OAuthError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Authentication failed") from exc
    info = token.get("userinfo") or {}
    email = info.get("email") or info.get("preferred_username") or ""
    if not email:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "No email claim in the sign-in token")
    user = CurrentUser(email=email.strip().lower(), name=info.get("name") or email)
    await _start_session(request, user, access, method="sso")
    return RedirectResponse(url=settings.FRONTEND_URL, status_code=status.HTTP_302_FOUND)


@router.post("/dev-login", response_model=MeResponse)
async def dev_login(
    body: DevLoginRequest, request: Request, access: AccessServiceDep
) -> MeResponse:
    """Sign in by email alone. Only for local demos; 404 unless dev login is on."""
    if not settings.dev_login_enabled:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not Found")
    user = CurrentUser(email=body.email.strip().lower(), name=body.name.strip())
    await _start_session(request, user, access, method="dev")
    return await me(user, access)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(request: Request) -> None:
    request.session.clear()


@router.get("/me", response_model=MeResponse)
async def me(user: CurrentUserDep, access: AccessServiceDep) -> MeResponse:
    """Who is signed in, whether they are an admin, and the scopes they hold."""
    grants = await access.grants_for(user.email)
    owners = await access.owners()
    return MeResponse(
        email=user.email,
        name=user.name,
        is_admin=is_admin(user.email),
        is_team_admin=await access.is_team_admin(user.email),
        grants=[
            GrantOut.model_validate(g).model_copy(update={"owner": owners.get(g.scope_path)})
            for g in grants
        ],
    )


async def _start_session(
    request: Request, user: CurrentUser, access: AccessService, *, method: str
) -> None:
    try:
        grants = await access.sign_in(user.email, user.name)
    except (MemoryNotConfiguredError, MemoryUnavailableError) as exc:
        logger.warning("default scope setup failed for %s", user.email, exc_info=True)
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Signed in, but your memory scope could not be set up. Try again shortly.",
        ) from exc
    request.session["user"] = user.model_dump()
    trace.log(
        "[AUTH]",
        trace_id=getattr(request.state, "trace_id", None),
        event="login",
        method=method,
        user=user.email,
        grants=len(grants),
    )
