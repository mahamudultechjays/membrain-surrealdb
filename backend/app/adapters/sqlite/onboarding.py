"""OnboardingRepository on the same local SQLite file as the scope grants.

Two tables: onboarding (one row per user) and user_vct_nodes (the nodes they
confirmed). Saving replaces both for that user in one transaction.
"""

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from app.adapters.sqlite.base import SqliteStore
from app.domain.ports.onboarding import MappedNode, OnboardingRecord

_SCHEMA = """
CREATE TABLE IF NOT EXISTS onboarding (
    email        TEXT PRIMARY KEY,
    primary_work TEXT NOT NULL,
    role         TEXT,
    team         TEXT,
    onboarded_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS user_vct_nodes (
    email        TEXT NOT NULL,
    node_id      TEXT NOT NULL,
    rank         INTEGER NOT NULL,
    is_primary   INTEGER NOT NULL CHECK (is_primary IN (0, 1)),
    confirmed_by TEXT NOT NULL CHECK (confirmed_by IN ('user', 'admin')),
    PRIMARY KEY (email, node_id)
);
"""


class SqliteOnboarding(SqliteStore):
    def __init__(self, path: str | Path) -> None:
        super().__init__(path, _SCHEMA)

    async def get(self, email: str) -> OnboardingRecord | None:
        key = email.strip().lower()
        rows = await self._query(
            "SELECT primary_work, role, team, onboarded_at FROM onboarding WHERE email = ?",
            (key,),
        )
        if not rows:
            return None
        nodes = await self._query(
            "SELECT node_id, rank, is_primary, confirmed_by FROM user_vct_nodes "
            "WHERE email = ? ORDER BY rank",
            (key,),
        )
        primary_work, role, team, onboarded_at = rows[0]
        return OnboardingRecord(
            email=key,
            primary_work=primary_work,
            role=role,
            team=team,
            onboarded_at=onboarded_at,
            nodes=[MappedNode(n, r, bool(p), by) for n, r, p, by in nodes],
        )

    async def save(self, record: OnboardingRecord) -> None:
        key = record.email.strip().lower()
        onboarded_at = record.onboarded_at or datetime.now(UTC).isoformat(timespec="seconds")

        def work(db: sqlite3.Connection) -> None:
            db.execute(
                "INSERT INTO onboarding (email, primary_work, role, team, onboarded_at) "
                "VALUES (?, ?, ?, ?, ?) ON CONFLICT (email) DO UPDATE SET "
                "primary_work = excluded.primary_work, role = excluded.role, "
                "team = excluded.team, onboarded_at = excluded.onboarded_at",
                (key, record.primary_work, record.role, record.team, onboarded_at),
            )
            db.execute("DELETE FROM user_vct_nodes WHERE email = ?", (key,))
            db.executemany(
                "INSERT INTO user_vct_nodes (email, node_id, rank, is_primary, confirmed_by) "
                "VALUES (?, ?, ?, ?, ?)",
                [(key, n.node_id, n.rank, int(n.is_primary), n.confirmed_by) for n in record.nodes],
            )

        await self._write(work)
