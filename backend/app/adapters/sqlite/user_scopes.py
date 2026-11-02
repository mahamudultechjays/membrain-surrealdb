"""UserScopeRepository on a local SQLite file: one table, user_scopes.

Each call opens its own connection in a worker thread, so the event loop never
blocks and no connection is shared across threads (":memory:" keeps one shared
connection instead, for tests). Emails are stored lowercased: they are the join key.
"""

import asyncio
import sqlite3
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from app.domain.ports.user_scopes import ScopeGrant

_SCHEMA = """
CREATE TABLE IF NOT EXISTS user_scopes (
    email      TEXT NOT NULL,
    name       TEXT NOT NULL,
    scope_path TEXT NOT NULL,
    access     TEXT NOT NULL CHECK (access IN ('read', 'write')),
    layer      TEXT NOT NULL CHECK (layer IN ('org', 'team', 'personal')),
    created_at TEXT NOT NULL,
    PRIMARY KEY (email, scope_path)
)
"""

_COLUMNS = "email, name, scope_path, access, layer"


class SqliteUserScopes:
    def __init__(self, path: str | Path) -> None:
        self._path = str(path)
        self._shared: sqlite3.Connection | None = None
        if self._path == ":memory:":
            self._shared = sqlite3.connect(":memory:", check_same_thread=False)
        else:
            Path(self._path).parent.mkdir(parents=True, exist_ok=True)
        self._run(lambda db: db.execute(_SCHEMA))

    async def grants_for(self, email: str) -> list[ScopeGrant]:
        rows = await self._query(
            f"SELECT {_COLUMNS} FROM user_scopes WHERE email = ? ORDER BY scope_path",
            (email.strip().lower(),),
        )
        return [_grant(row) for row in rows]

    async def all_grants(self) -> list[ScopeGrant]:
        rows = await self._query(
            f"SELECT {_COLUMNS} FROM user_scopes ORDER BY email, scope_path", ()
        )
        return [_grant(row) for row in rows]

    async def put(self, grant: ScopeGrant) -> None:
        params = (
            grant.email.strip().lower(),
            grant.name,
            grant.scope_path,
            grant.access,
            grant.layer,
            datetime.now(UTC).isoformat(timespec="seconds"),
        )
        await asyncio.to_thread(
            self._run,
            lambda db: db.execute(
                "INSERT INTO user_scopes (email, name, scope_path, access, layer, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT (email, scope_path) DO UPDATE SET "
                "access = excluded.access, layer = excluded.layer, name = excluded.name",
                params,
            ),
        )

    async def remove(self, email: str, scope_path: str) -> bool:
        cursor = await asyncio.to_thread(
            self._run,
            lambda db: db.execute(
                "DELETE FROM user_scopes WHERE email = ? AND scope_path = ?",
                (email.strip().lower(), scope_path),
            ),
        )
        return bool(cursor.rowcount > 0)

    async def _query(self, sql: str, params: tuple[str, ...]) -> list[tuple[str, ...]]:
        return await asyncio.to_thread(self._run, lambda db: db.execute(sql, params).fetchall())

    def _run[T](self, work: Callable[[sqlite3.Connection], T]) -> T:
        if self._shared is not None:
            with self._shared:
                return work(self._shared)
        db = sqlite3.connect(self._path)
        try:
            with db:
                return work(db)
        finally:
            db.close()


def _grant(row: tuple[str, ...]) -> ScopeGrant:
    email, name, scope_path, access, layer = row
    return ScopeGrant(
        email=email,
        name=name,
        scope_path=scope_path,
        access=access,  # type: ignore[arg-type]  # the CHECK constraint keeps it valid
        layer=layer,  # type: ignore[arg-type]
    )
