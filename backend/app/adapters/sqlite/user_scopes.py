"""UserScopeRepository on a local SQLite file: one table, user_scopes.

Emails are stored lowercased: they are the join key.
"""

from datetime import UTC, datetime
from pathlib import Path

from app.adapters.sqlite.base import SqliteStore
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
);
CREATE TABLE IF NOT EXISTS user_roles (
    email      TEXT NOT NULL,
    role       TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (email, role)
);
"""

_COLUMNS = "email, name, scope_path, access, layer"


class SqliteUserScopes(SqliteStore):
    def __init__(self, path: str | Path) -> None:
        super().__init__(path, _SCHEMA)

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
        await self._write(
            lambda db: db.execute(
                "INSERT INTO user_scopes (email, name, scope_path, access, layer, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT (email, scope_path) DO UPDATE SET "
                "access = excluded.access, layer = excluded.layer, name = excluded.name",
                params,
            )
        )

    async def remove(self, email: str, scope_path: str) -> bool:
        cursor = await self._write(
            lambda db: db.execute(
                "DELETE FROM user_scopes WHERE email = ? AND scope_path = ?",
                (email.strip().lower(), scope_path),
            )
        )
        return bool(cursor.rowcount > 0)

    async def roles_for(self, email: str) -> set[str]:
        rows = await self._query(
            "SELECT role FROM user_roles WHERE email = ?", (email.strip().lower(),)
        )
        return {r[0] for r in rows}

    async def set_role(self, email: str, role: str, on: bool) -> None:
        key = (email.strip().lower(), role)
        if on:
            now = datetime.now(UTC).isoformat(timespec="seconds")
            await self._write(
                lambda db: db.execute(
                    "INSERT OR IGNORE INTO user_roles (email, role, created_at) VALUES (?, ?, ?)",
                    (*key, now),
                )
            )
        else:
            await self._write(
                lambda db: db.execute("DELETE FROM user_roles WHERE email = ? AND role = ?", key)
            )

    async def emails_with_role(self, role: str) -> list[str]:
        rows = await self._query(
            "SELECT email FROM user_roles WHERE role = ? ORDER BY email", (role,)
        )
        return [r[0] for r in rows]


def _grant(row: tuple[str, ...]) -> ScopeGrant:
    email, name, scope_path, access, layer = row
    return ScopeGrant(
        email=email,
        name=name,
        scope_path=scope_path,
        access=access,  # type: ignore[arg-type]  # the CHECK constraint keeps it valid
        layer=layer,  # type: ignore[arg-type]
    )
