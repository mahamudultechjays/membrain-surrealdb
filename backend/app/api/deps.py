"""FastAPI dependency wiring — bridges the framework to the composition root.

Concrete adapter selection lives in app/composition.py; this module only
adapts those factories to FastAPI's Depends() mechanism.
"""

from typing import Annotated

from fastapi import Depends, HTTPException, Request, status

from app.composition import (
    get_access_service,
    get_chat_sessions,
    get_document_store,
    get_memory_brain,
    get_memory_capture,
    get_memory_chat,
    get_memory_graph,
    get_memory_probe,
    get_memory_recall,
    get_preview_cache,
    get_scope_registry,
    get_text_reader,
)
from app.core.config import settings
from app.domain.ports.document_store import DocumentStore
from app.domain.ports.memory_brain import MemoryBrain
from app.domain.ports.memory_capture import MemoryCapture
from app.domain.ports.memory_chat import MemoryChat
from app.domain.ports.memory_graph import MemoryGraph
from app.domain.ports.memory_probe import MemoryProbe
from app.domain.ports.memory_recall import MemoryRecall
from app.domain.ports.scope_registry import ScopeRegistry
from app.domain.ports.text_reader import DocumentTextReader
from app.schemas.auth import CurrentUser
from app.services.access import AccessService
from app.services.capture_flow import PreviewCache
from app.services.chat_flow import ChatSessions

MemoryProbeDep = Annotated[MemoryProbe, Depends(get_memory_probe)]
MemoryCaptureDep = Annotated[MemoryCapture, Depends(get_memory_capture)]
DocumentStoreDep = Annotated[DocumentStore, Depends(get_document_store)]
TextReaderDep = Annotated[DocumentTextReader, Depends(get_text_reader)]
MemoryBrainDep = Annotated[MemoryBrain, Depends(get_memory_brain)]
MemoryGraphDep = Annotated[MemoryGraph, Depends(get_memory_graph)]
PreviewCacheDep = Annotated[PreviewCache, Depends(get_preview_cache)]
MemoryRecallDep = Annotated[MemoryRecall, Depends(get_memory_recall)]
ScopeRegistryDep = Annotated[ScopeRegistry, Depends(get_scope_registry)]
AccessServiceDep = Annotated[AccessService, Depends(get_access_service)]
MemoryChatDep = Annotated[MemoryChat, Depends(get_memory_chat)]
ChatSessionsDep = Annotated[ChatSessions, Depends(get_chat_sessions)]


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
