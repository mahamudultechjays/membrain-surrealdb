from typing import Any

import pytest

from app.adapters.db.surreal import connection as module
from app.adapters.db.surreal.connection import SurrealConnection


class FakeClient:
    def __init__(self, fail_queries: bool = False) -> None:
        self.fail_queries = fail_queries
        self.closed = False

    async def connect(self, url: str) -> None: ...

    async def signin(self, vars: dict[str, Any]) -> None: ...

    async def use(self, namespace: str, database: str) -> None: ...

    async def query(self, query: str) -> bool:
        if self.fail_queries:
            raise ConnectionError("socket closed")
        return True

    async def close(self) -> None:
        self.closed = True


class ClientFactory:
    """Stands in for AsyncSurreal; records every client the adapter creates."""

    def __init__(self) -> None:
        self.created: list[FakeClient] = []
        self.fail_next = False

    def __call__(self, url: str) -> FakeClient:
        client = FakeClient(fail_queries=self.fail_next)
        self.created.append(client)
        return client


@pytest.fixture
def clients(monkeypatch: pytest.MonkeyPatch) -> ClientFactory:
    factory = ClientFactory()
    monkeypatch.setattr(module, "AsyncSurreal", factory)
    return factory


def make_connection() -> SurrealConnection:
    return SurrealConnection("ws://db/rpc", "ns", "db", "user", "pass")


async def test_ping_reuses_one_client(clients: ClientFactory) -> None:
    connection = make_connection()

    assert await connection.ping()
    assert await connection.ping()

    assert len(clients.created) == 1


async def test_failed_ping_reconnects_on_next_call(clients: ClientFactory) -> None:
    connection = make_connection()
    clients.fail_next = True
    assert not await connection.ping()
    assert clients.created[0].closed

    clients.fail_next = False
    assert await connection.ping()

    assert len(clients.created) == 2


async def test_close_is_idempotent(clients: ClientFactory) -> None:
    connection = make_connection()
    await connection.connect()

    await connection.close()
    await connection.close()

    assert clients.created[0].closed
