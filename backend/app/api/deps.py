"""FastAPI dependency wiring — bridges the framework to the composition root.

Concrete adapter selection lives in app/composition.py; this module only
adapts those factories to FastAPI's Depends() mechanism.
"""

from typing import Annotated

from fastapi import Depends, HTTPException, Request, status

from app.composition import (
    get_access_service,
    get_active_scopes,
    get_document_store,
    get_memory_capture,
    get_memory_graph,
    get_memory_probe,
    get_preview_cache,
    get_recall_factory,
    get_scope_directory,
    get_text_reader,
)
from app.core.config import settings
from app.domain.errors import UnknownScopeError
from app.domain.ports.document_store import DocumentStore
from app.domain.ports.memory_capture import MemoryCapture
from app.domain.ports.memory_graph import MemoryGraph
from app.domain.ports.memory_probe import MemoryProbe
from app.domain.ports.memory_recall import RecallFactory
from app.domain.ports.text_reader import DocumentTextReader
from app.schemas.auth import CurrentUser
from app.services.access import AccessService
from app.services.capture_flow import PreviewCache
from app.services.scopes import ActiveScopes, ScopeDirectory

MemoryProbeDep = Annotated[MemoryProbe, Depends(get_memory_probe)]
MemoryCaptureDep = Annotated[MemoryCapture, Depends(get_memory_capture)]
DocumentStoreDep = Annotated[DocumentStore, Depends(get_document_store)]
TextReaderDep = Annotated[DocumentTextReader, Depends(get_text_reader)]
MemoryGraphDep = Annotated[MemoryGraph, Depends(get_memory_graph)]
ScopeDirectoryDep = Annotated[ScopeDirectory, Depends(get_scope_directory)]
PreviewCacheDep = Annotated[PreviewCache, Depends(get_preview_cache)]
RecallFactoryDep = Annotated[RecallFactory, Depends(get_recall_factory)]
ActiveScopesDep = Annotated[ActiveScopes, Depends(get_active_scopes)]
AccessServiceDep = Annotated[AccessService, Depends(get_access_service)]


async def get_current_user(request: Request) -> CurrentUser:
    """The signed-in user from the session cookie set at login; 401 without one."""
    data = request.session.get("user")
    if not data:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not signed in.")
    return CurrentUser(**data)


CurrentUserDep = Annotated[CurrentUser, Depends(get_current_user)]


def is_admin(email: str) -> bool:
    return email.strip().lower() in settings.admin_emails()


async def require_admin(user: CurrentUserDep) -> CurrentUser:
    """401 when signed out (via get_current_user), 403 when not on ADMIN_EMAILS."""
    if not is_admin(user.email):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admins only.")
    return user


AdminUserDep = Annotated[CurrentUser, Depends(require_admin)]


def authorize_scopes(request: Request, directory: ScopeDirectory, scopes: list[str]) -> None:
    """422 for scopes the demo doesn't know."""
    try:
        for scope in scopes:
            directory.get(scope)
    except UnknownScopeError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"Unknown scope: {exc}") from exc
