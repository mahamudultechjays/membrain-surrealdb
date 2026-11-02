"""Composition root: the only module that binds concrete adapters to ports."""

from functools import lru_cache

from surrealdb_memory import AsyncMemory

from app.adapters.agent_memory import (
    AgentMemoryCapture,
    AgentMemoryDocuments,
    AgentMemoryGraph,
    AgentMemoryProbe,
    AgentMemoryRecall,
    NotConfiguredCapture,
    NotConfiguredDocuments,
    NotConfiguredGraph,
    NotConfiguredProbe,
    NotConfiguredRecall,
)
from app.adapters.files import PdfAndTextReader
from app.core.config import settings
from app.domain.ports.document_store import DocumentStore, DocumentStoreFactory
from app.domain.ports.memory_capture import CaptureFactory, MemoryCapture
from app.domain.ports.memory_graph import MemoryGraph
from app.domain.ports.memory_probe import MemoryProbe
from app.domain.ports.memory_recall import MemoryRecall, RecallFactory
from app.domain.ports.text_reader import DocumentTextReader
from app.services.capture_flow import PreviewCache
from app.services.scopes import ScopeDirectory

_user_clients: dict[str, AsyncMemory] = {}


def _new_client(api_key: str) -> AsyncMemory | None:
    endpoint = settings.AGENT_MEMORY_ENDPOINT
    context = settings.AGENT_MEMORY_CONTEXT
    if not (endpoint and context and api_key):
        return None
    return AsyncMemory(
        context,
        endpoint=endpoint.rstrip("/"),
        api_key=api_key,
        timeout=settings.AGENT_MEMORY_TIMEOUT_SECONDS,
    )


@lru_cache
def get_agent_memory_client() -> AsyncMemory | None:
    """One client per process, or None until all AGENT_MEMORY_* settings are set.

    The client opens its HTTP session lazily on first use; the app lifespan
    closes it on shutdown.
    """
    api_key = settings.AGENT_MEMORY_API_KEY
    return _new_client(api_key.get_secret_value()) if api_key else None


def client_for_scope(scope: str) -> AsyncMemory | None:
    """The user's own key when one is set, so Agent Memory enforces that user's grant.

    Without one, the shared key is used and only the scopes/lens the app passes
    keep users apart.
    """
    user_key = {s: k for k, s in settings.api_key_scopes().items()}.get(scope)
    if not user_key:
        return get_agent_memory_client()
    if user_key not in _user_clients:
        client = _new_client(user_key)
        if client is None:
            return None
        _user_clients[user_key] = client
    return _user_clients[user_key]


async def close_clients() -> None:
    clients = [get_agent_memory_client(), *_user_clients.values()]
    _user_clients.clear()
    for client in clients:
        if client is not None:
            await client.close()


@lru_cache
def get_scope_directory() -> ScopeDirectory:
    return ScopeDirectory()


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


def get_capture_factory() -> CaptureFactory:
    def for_scope(scope: str) -> MemoryCapture:
        client = client_for_scope(scope)
        return AgentMemoryCapture(client) if client else NotConfiguredCapture()

    return for_scope


def get_document_store_factory() -> DocumentStoreFactory:
    def for_scope(scope: str) -> DocumentStore:
        client = client_for_scope(scope)
        return AgentMemoryDocuments(client) if client else NotConfiguredDocuments()

    return for_scope


def get_recall_factory() -> RecallFactory:
    def for_scope(scope: str) -> MemoryRecall:
        client = client_for_scope(scope)
        return AgentMemoryRecall(client) if client else NotConfiguredRecall()

    return for_scope


@lru_cache
def get_preview_cache() -> PreviewCache:
    return PreviewCache()


def get_text_reader() -> DocumentTextReader:
    return PdfAndTextReader()
