"""Composition root: the only module that binds concrete adapters to ports."""

from functools import lru_cache

from surrealdb_memory import AsyncMemory

from app.adapters.agent_memory import (
    AgentMemoryBrain,
    AgentMemoryCapture,
    AgentMemoryChat,
    AgentMemoryDocuments,
    AgentMemoryGraph,
    AgentMemoryLab,
    AgentMemoryProbe,
    AgentMemoryRecall,
    AgentMemoryScopeRegistry,
    NotConfiguredBrain,
    NotConfiguredCapture,
    NotConfiguredChat,
    NotConfiguredDocuments,
    NotConfiguredGraph,
    NotConfiguredLab,
    NotConfiguredProbe,
    NotConfiguredRecall,
    NotConfiguredScopeRegistry,
)
from app.adapters.files import PdfAndTextReader
from app.adapters.sqlite import SqliteUserScopes
from app.core.config import settings
from app.domain.ports.document_store import DocumentStore
from app.domain.ports.memory_brain import MemoryBrain
from app.domain.ports.memory_capture import MemoryCapture
from app.domain.ports.memory_graph import MemoryGraph
from app.domain.ports.memory_probe import MemoryProbe
from app.domain.ports.memory_recall import MemoryRecall
from app.domain.ports.scope_registry import ScopeRegistry
from app.domain.ports.text_reader import DocumentTextReader
from app.domain.ports.user_scopes import UserScopeRepository
from app.services.access import AccessService
from app.services.capture_flow import PreviewCache
from app.services.chat_flow import ChatSessions


@lru_cache
def get_agent_memory_client() -> AsyncMemory | None:
    """The one admin-key client per process, or None until all AGENT_MEMORY_* are set.

    Every user goes through this key. Isolation comes from the scopes and lens
    our backend passes on each call, never from per-user keys.
    The client opens its HTTP session lazily on first use; the app lifespan
    closes it on shutdown.
    """
    endpoint = settings.AGENT_MEMORY_ENDPOINT
    context = settings.AGENT_MEMORY_CONTEXT
    api_key = settings.AGENT_MEMORY_API_KEY
    if not (endpoint and context and api_key and api_key.get_secret_value()):
        return None
    return AsyncMemory(
        context,
        endpoint=endpoint.rstrip("/"),
        api_key=api_key.get_secret_value(),
        timeout=settings.AGENT_MEMORY_TIMEOUT_SECONDS,
    )


def _connect(api_key: str, *, timeout: float | None = None) -> AsyncMemory:
    """A client on the same Context as the admin client, with another key."""
    return AsyncMemory(
        settings.AGENT_MEMORY_CONTEXT or "",
        endpoint=(settings.AGENT_MEMORY_ENDPOINT or "").rstrip("/"),
        api_key=api_key,
        timeout=timeout or settings.AGENT_MEMORY_TIMEOUT_SECONDS,
    )


# Consolidation and reflection run a model over the scope: allow minutes, not seconds.
LAB_TIMEOUT_SECONDS = 180.0


async def close_clients() -> None:
    # Chat and lab first: deleting their minted keys needs the admin client still open.
    if get_memory_chat.cache_info().currsize:
        await get_memory_chat().close()
    if get_memory_lab.cache_info().currsize:
        await get_memory_lab().close()
    client = get_agent_memory_client()
    if client is not None:
        await client.close()


def get_memory_probe() -> MemoryProbe:
    client = get_agent_memory_client()
    return AgentMemoryProbe(client) if client else NotConfiguredProbe()


def get_memory_capture() -> MemoryCapture:
    client = get_agent_memory_client()
    return AgentMemoryCapture(client) if client else NotConfiguredCapture()


def get_document_store() -> DocumentStore:
    client = get_agent_memory_client()
    return AgentMemoryDocuments(client) if client else NotConfiguredDocuments()


def get_memory_brain() -> MemoryBrain:
    client = get_agent_memory_client()
    return AgentMemoryBrain(client) if client else NotConfiguredBrain()


def get_memory_graph() -> MemoryGraph:
    client = get_agent_memory_client()
    return AgentMemoryGraph(client) if client else NotConfiguredGraph()


def get_memory_recall() -> MemoryRecall:
    client = get_agent_memory_client()
    return AgentMemoryRecall(client) if client else NotConfiguredRecall()


@lru_cache
def get_memory_chat() -> AgentMemoryChat | NotConfiguredChat:
    """One per process: it holds the keys minted for each user's chats."""
    client = get_agent_memory_client()
    return AgentMemoryChat(client, _connect) if client else NotConfiguredChat()


@lru_cache
def get_memory_lab() -> AgentMemoryLab | NotConfiguredLab:
    """One per process: it holds the keys minted for each lab scope."""
    client = get_agent_memory_client()
    if client is None:
        return NotConfiguredLab()

    def connect(key: str) -> AsyncMemory:
        return _connect(key, timeout=LAB_TIMEOUT_SECONDS)

    admin_key = settings.AGENT_MEMORY_API_KEY
    whole = connect(admin_key.get_secret_value()) if admin_key else None
    return AgentMemoryLab(client, connect, whole=whole)


@lru_cache
def get_chat_sessions() -> ChatSessions:
    return ChatSessions()


@lru_cache
def get_user_scope_repository() -> UserScopeRepository:
    return SqliteUserScopes(settings.USER_SCOPES_DB_PATH)


def get_scope_registry() -> ScopeRegistry:
    client = get_agent_memory_client()
    return AgentMemoryScopeRegistry(client) if client else NotConfiguredScopeRegistry()


def get_access_service() -> AccessService:
    return AccessService(
        get_user_scope_repository(),
        get_scope_registry(),
        org_scope=settings.ORG_SCOPE,
        user_root=settings.USER_SCOPE_ROOT,
    )


@lru_cache
def get_preview_cache() -> PreviewCache:
    return PreviewCache()


def get_text_reader() -> DocumentTextReader:
    return PdfAndTextReader()
