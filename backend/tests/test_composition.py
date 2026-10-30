from collections.abc import Iterator

import pytest
from pydantic import SecretStr

from app import composition
from app.adapters.agent_memory import AgentMemoryProbe, NotConfiguredProbe
from app.core.config import settings


@pytest.fixture(autouse=True)
def fresh_client_cache() -> Iterator[None]:
    composition.get_agent_memory_client.cache_clear()
    yield
    composition.get_agent_memory_client.cache_clear()


def test_missing_settings_give_not_configured_probe(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "AGENT_MEMORY_API_KEY", None)

    assert composition.get_agent_memory_client() is None
    assert isinstance(composition.get_memory_probe(), NotConfiguredProbe)


def test_complete_settings_give_real_probe(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "AGENT_MEMORY_ENDPOINT", "https://memory.example.com/")
    monkeypatch.setattr(settings, "AGENT_MEMORY_CONTEXT", "poc")
    monkeypatch.setattr(settings, "AGENT_MEMORY_API_KEY", SecretStr("secret"))

    client = composition.get_agent_memory_client()

    assert client is not None
    assert client.context_id == "poc"
    assert client.endpoint == "https://memory.example.com"
    assert isinstance(composition.get_memory_probe(), AgentMemoryProbe)
