from collections.abc import Iterator

import pytest
from pydantic import SecretStr

from app import composition
from app.adapters.agent_memory import (
    AgentMemoryCapture,
    AgentMemoryChat,
    AgentMemoryDocuments,
    AgentMemoryGraph,
    AgentMemoryProbe,
    NotConfiguredCapture,
    NotConfiguredChat,
    NotConfiguredDocuments,
    NotConfiguredGraph,
    NotConfiguredProbe,
)
from app.adapters.files import PdfAndTextReader
from app.core.config import settings


@pytest.fixture(autouse=True)
def fresh_client_cache() -> Iterator[None]:
    composition.get_agent_memory_client.cache_clear()
    composition.get_memory_chat.cache_clear()
    yield
    composition.get_agent_memory_client.cache_clear()
    composition.get_memory_chat.cache_clear()


def test_chat_is_not_configured_without_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "AGENT_MEMORY_API_KEY", None)

    assert isinstance(composition.get_memory_chat(), NotConfiguredChat)


def test_chat_mints_keys_on_the_same_context(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "AGENT_MEMORY_ENDPOINT", "https://memory.example.com/")
    monkeypatch.setattr(settings, "AGENT_MEMORY_CONTEXT", "poc")
    monkeypatch.setattr(settings, "AGENT_MEMORY_API_KEY", SecretStr("secret"))

    user_client = composition._connect("minted")

    assert isinstance(composition.get_memory_chat(), AgentMemoryChat)
    assert (user_client.context_id, user_client.endpoint) == ("poc", "https://memory.example.com")


def test_missing_settings_give_not_configured_probe(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "AGENT_MEMORY_API_KEY", None)

    assert composition.get_agent_memory_client() is None
    assert isinstance(composition.get_memory_probe(), NotConfiguredProbe)
    assert isinstance(composition.get_memory_capture(), NotConfiguredCapture)
    assert isinstance(composition.get_document_store(), NotConfiguredDocuments)
    assert isinstance(composition.get_text_reader(), PdfAndTextReader)
    assert isinstance(composition.get_memory_graph(), NotConfiguredGraph)


def test_complete_settings_give_real_probe(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "AGENT_MEMORY_ENDPOINT", "https://memory.example.com/")
    monkeypatch.setattr(settings, "AGENT_MEMORY_CONTEXT", "poc")
    monkeypatch.setattr(settings, "AGENT_MEMORY_API_KEY", SecretStr("secret"))

    client = composition.get_agent_memory_client()

    assert client is not None
    assert client.context_id == "poc"
    assert client.endpoint == "https://memory.example.com"
    assert isinstance(composition.get_memory_probe(), AgentMemoryProbe)
    assert isinstance(composition.get_memory_capture(), AgentMemoryCapture)
    assert isinstance(composition.get_document_store(), AgentMemoryDocuments)
    assert isinstance(composition.get_memory_graph(), AgentMemoryGraph)
