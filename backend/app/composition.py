"""Composition root: the only module that binds concrete adapters to ports."""

from functools import lru_cache

from surrealdb_memory import AsyncMemory

from app.adapters.agent_memory import (
    AgentMemoryCapture,
    AgentMemoryDocuments,
    AgentMemoryGraph,
    AgentMemoryProbe,
    AgentMemoryRecall,
    AgentMemoryScopeRegistry,
    NotConfiguredCapture,
    NotConfiguredDocuments,
    NotConfiguredGraph,
    NotConfiguredProbe,
    NotConfiguredRecall,
    NotConfiguredScopeRegistry,
)
from app.adapters.files import PdfAndTextReader
from app.adapters.sqlite import SqliteUserScopes
from app.core.config import settings
from app.domain.ports.document_store import DocumentStore
from app.domain.ports.memory_capture import MemoryCapture
from app.domain.ports.memory_graph import MemoryGraph
from app.domain.ports.memory_probe import MemoryProbe
from app.domain.ports.memory_recall import MemoryRecall
from app.domain.ports.scope_registry import ScopeRegistry
from app.domain.ports.text_reader import DocumentTextReader
from app.domain.ports.user_scopes import UserScopeRepository
from app.services.access import AccessService
from app.services.capture_flow import PreviewCache


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


async def close_clients() -> None:
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


def get_memory_graph() -> MemoryGraph:
    client = get_agent_memory_client()
    return AgentMemoryGraph(client) if client else NotConfiguredGraph()


def get_memory_recall() -> MemoryRecall:
    client = get_agent_memory_client()
    return AgentMemoryRecall(client) if client else NotConfiguredRecall()


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
