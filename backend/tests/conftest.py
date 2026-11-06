from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.adapters.sqlite import SqliteFactTags, SqliteUserScopes
from app.composition import get_access_service, get_fact_tag_repository, get_memory_probe
from app.core.config import settings
from app.domain.ports.memory_probe import MemoryStatus
from app.main import app
from app.services.access import AccessService


class FakeProbe:
    def __init__(self, status: MemoryStatus = "ok") -> None:
        self.status: MemoryStatus = status

    async def check(self) -> MemoryStatus:
        return self.status


class FakeRegistry:
    """Records the scope paths that would be registered in Agent Memory."""

    def __init__(self) -> None:
        self.ensured: list[str] = []
        self.error: Exception | None = None

    async def list(self, prefix: str = "") -> list[str]:
        return [p for p in self.ensured if p.startswith(prefix)]

    async def ensure(self, path: str) -> None:
        if self.error:
            raise self.error
        self.ensured.append(path)


@pytest.fixture
def probe() -> FakeProbe:
    return FakeProbe()


@pytest.fixture
def client(probe: FakeProbe) -> Iterator[TestClient]:
    app.dependency_overrides[get_memory_probe] = lambda: probe
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def registry() -> FakeRegistry:
    return FakeRegistry()


@pytest.fixture
def tags() -> SqliteFactTags:
    """VCT fact tags on an in-memory table."""
    return SqliteFactTags(":memory:")


@pytest.fixture
def access(
    registry: FakeRegistry, tags: SqliteFactTags, monkeypatch: pytest.MonkeyPatch
) -> AccessService:
    """A real AccessService on an in-memory table, wired into the app, with dev
    login switched on and admin@x.com as the only admin."""
    service = AccessService(
        SqliteUserScopes(":memory:"),
        registry,
        org_scope="org/spreetail",
        user_root="org/spreetail/user",
    )
    app.dependency_overrides[get_access_service] = lambda: service
    app.dependency_overrides[get_fact_tag_repository] = lambda: tags
    monkeypatch.setattr(settings, "DEV_LOGIN_ENABLED", True)
    monkeypatch.setattr(settings, "ADMIN_EMAILS", "admin@x.com")
    return service


def sign_in(client: TestClient, email: str, name: str) -> None:
    """Start a session the way the login screen's dev login does."""
    response = client.post("/api/v1/auth/dev-login", json={"email": email, "name": name})
    assert response.status_code == 200, response.text
