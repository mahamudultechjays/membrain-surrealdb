"""PromotionRepository on the same local SQLite file as the scope grants.

Three tables (spec section 4): statement, fact_group, review_item. Beyond the
spec's fields: statement.norm_value (the value in its topic's form),
fact_group.rule_entity_type, review_item.closed_ref and created_at.
"""

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.adapters.sqlite.base import SqliteStore
from app.domain.errors import PromotionStateError
from app.domain.ports.promotion import FactGroup, ReviewItem, ReviewStatus, Statement
from app.domain.promotion import Stance

_SCHEMA = """
CREATE TABLE IF NOT EXISTS statement (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    user         TEXT NOT NULL,
    scope        TEXT NOT NULL,
    memory_ref   TEXT NOT NULL UNIQUE,
    source       TEXT NOT NULL CHECK (source IN ('chat', 'app')),
    text         TEXT NOT NULL,
    entity       TEXT NOT NULL,
    key          TEXT NOT NULL,
    value        TEXT NOT NULL,
    said_at      TEXT NOT NULL,
    group_id     INTEGER,
    stance       TEXT CHECK (stance IN ('for', 'against')),
    norm_value   TEXT,
    replaced_at  TEXT,
    processed_at TEXT
);
CREATE INDEX IF NOT EXISTS statement_scope ON statement (scope);
CREATE INDEX IF NOT EXISTS statement_group ON statement (group_id);
CREATE TABLE IF NOT EXISTS fact_group (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    label            TEXT NOT NULL,
    subject          TEXT NOT NULL,
    aliases          TEXT NOT NULL DEFAULT '[]',
    rule_entity_type TEXT NOT NULL,
    rule_entity      TEXT NOT NULL,
    rule_key         TEXT NOT NULL,
    created_at       TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS review_item (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    kind              TEXT NOT NULL CHECK (kind IN ('candidate', 'flag')),
    group_id          INTEGER NOT NULL,
    value             TEXT NOT NULL,
    score_when_listed REAL NOT NULL,
    status            TEXT NOT NULL
        CHECK (status IN ('open', 'active', 'closed', 'rejected', 'dropped', 'kept')),
    decided_by        TEXT,
    decided_at        TEXT,
    memory_ref        TEXT,
    rule_id           INTEGER,
    closed_ref        TEXT,
    created_at        TEXT NOT NULL,
    rule_entity_type  TEXT,
    rule_entity       TEXT,
    rule_key          TEXT
);
"""

_ST = (
    "id, user, scope, memory_ref, source, text, entity, key, value, said_at, "
    "group_id, stance, norm_value, replaced_at, processed_at"
)
_GR = "id, label, subject, aliases, rule_entity_type, rule_entity, rule_key, created_at"
_RI = (
    "id, kind, group_id, value, score_when_listed, status, decided_by, decided_at, "
    "memory_ref, rule_id, closed_ref, created_at, rule_entity_type, rule_entity, rule_key"
)


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _marks(n: int) -> str:
    return ",".join("?" * n)


def _statement(r: tuple[Any, ...]) -> Statement:
    return Statement(
        id=r[0], user=r[1], scope=r[2], memory_ref=r[3], source=r[4], text=r[5],
        entity=r[6], key=r[7], value=r[8], said_at=r[9], group_id=r[10], stance=r[11],
        norm_value=r[12], replaced_at=r[13], processed_at=r[14],
    )  # fmt: skip


def _group(r: tuple[Any, ...]) -> FactGroup:
    return FactGroup(
        id=r[0], label=r[1], subject=r[2], aliases=tuple(json.loads(r[3] or "[]")),
        rule_entity_type=r[4], rule_entity=r[5], rule_key=r[6], created_at=r[7],
    )  # fmt: skip


def _item(r: tuple[Any, ...]) -> ReviewItem:
    return ReviewItem(
        id=r[0], kind=r[1], group_id=r[2], value=r[3], score_when_listed=r[4], status=r[5],
        decided_by=r[6], decided_at=r[7], memory_ref=r[8], rule_id=r[9], closed_ref=r[10],
        created_at=r[11], rule_entity_type=r[12], rule_entity=r[13], rule_key=r[14],
    )  # fmt: skip


class SqlitePromotion(SqliteStore):
    def __init__(self, path: str | Path) -> None:
        super().__init__(path, _SCHEMA)

    async def known_refs(self, refs: list[str]) -> set[str]:
        if not refs:
            return set()
        rows = await self._query(
            f"SELECT memory_ref FROM statement WHERE memory_ref IN ({_marks(len(refs))})",
            tuple(refs),
        )
        return {r[0] for r in rows}

    async def add_statements(self, rows: list[Statement]) -> int:
        def work(db: sqlite3.Connection) -> int:
            added = 0
            for s in rows:
                cur = db.execute(
                    "INSERT OR IGNORE INTO statement (user, scope, memory_ref, source, text, "
                    "entity, key, value, said_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (s.user, s.scope, s.memory_ref, s.source, s.text, s.entity, s.key, s.value,
                     s.said_at),
                )  # fmt: skip
                added += cur.rowcount
            return added

        return await self._write(work)

    async def mark_replaced(self, refs: list[str], at: str) -> int:
        if not refs:
            return 0
        return await self._write(
            lambda db: (
                db.execute(
                    f"UPDATE statement SET replaced_at = ? WHERE replaced_at IS NULL "
                    f"AND memory_ref IN ({_marks(len(refs))})",
                    (at, *refs),
                ).rowcount
            )
        )

    async def live_refs(self, scopes: list[str]) -> set[str]:
        if not scopes:
            return set()
        rows = await self._query(
            f"SELECT memory_ref FROM statement WHERE replaced_at IS NULL "
            f"AND scope IN ({_marks(len(scopes))})",
            tuple(scopes),
        )
        return {r[0] for r in rows}

    async def live_refs_except(self, scopes: list[str]) -> set[str]:
        rows = await self._query(
            f"SELECT memory_ref FROM statement WHERE replaced_at IS NULL "
            f"AND scope NOT IN ({_marks(len(scopes))})",
            tuple(scopes),
        )
        return {r[0] for r in rows}

    async def revive(self, refs: list[str]) -> int:
        if not refs:
            return 0
        return await self._write(
            lambda db: (
                db.execute(
                    f"UPDATE statement SET replaced_at = NULL WHERE replaced_at IS NOT NULL "
                    f"AND memory_ref IN ({_marks(len(refs))})",
                    tuple(refs),
                ).rowcount
            )
        )

    async def unprocessed(self, limit: int) -> list[Statement]:
        rows = await self._query(
            f"SELECT {_ST} FROM statement WHERE replaced_at IS NULL AND processed_at IS NULL "
            "ORDER BY said_at, id LIMIT ?",
            (limit,),
        )
        return [_statement(r) for r in rows]

    async def set_grouping(self, rows: list[tuple[int, int, str, Stance]], at: str) -> None:
        await self._write(
            lambda db: db.executemany(
                "UPDATE statement SET group_id = ?, norm_value = ?, stance = ?, processed_at = ? "
                "WHERE id = ?",
                [(gid, value, stance, at, sid) for sid, gid, value, stance in rows],
            )
        )

    async def counted(self) -> list[Statement]:
        rows = await self._query(
            f"SELECT {_ST} FROM statement WHERE replaced_at IS NULL AND group_id IS NOT NULL "
            "ORDER BY said_at, id",
            (),
        )
        return [_statement(r) for r in rows]

    async def groups(self) -> list[FactGroup]:
        return [
            _group(r) for r in await self._query(f"SELECT {_GR} FROM fact_group ORDER BY id", ())
        ]

    async def groups_for_subjects(self, subjects: set[str]) -> list[FactGroup]:
        return [
            g for g in await self.groups() if g.subject in subjects or subjects & set(g.aliases)
        ]

    async def add_group(self, group: FactGroup) -> int:
        def work(db: sqlite3.Connection) -> int:
            cur = db.execute(
                "INSERT INTO fact_group (label, subject, aliases, rule_entity_type, rule_entity, "
                "rule_key, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (group.label, group.subject, json.dumps(list(group.aliases)),
                 group.rule_entity_type, group.rule_entity, group.rule_key, _now()),
            )  # fmt: skip
            return int(cur.lastrowid or 0)

        return await self._write(work)

    async def add_alias(self, group_id: int, alias: str) -> None:
        def work(db: sqlite3.Connection) -> None:
            row = db.execute(
                "SELECT subject, aliases FROM fact_group WHERE id = ?", (group_id,)
            ).fetchone()
            if row is None:
                return
            aliases = json.loads(row[1] or "[]")
            if alias == row[0] or alias in aliases:
                return
            db.execute(
                "UPDATE fact_group SET aliases = ? WHERE id = ?",
                (json.dumps([*aliases, alias]), group_id),
            )

        await self._write(work)

    async def update_rule(
        self, group_id: int, *, label: str, entity_type: str, entity: str, key: str
    ) -> None:
        await self._write(
            lambda db: db.execute(
                "UPDATE fact_group SET label = ?, rule_entity_type = ?, rule_entity = ?, "
                "rule_key = ? WHERE id = ?",
                (label, entity_type, entity, key, group_id),
            )
        )

    async def review_items(self) -> list[ReviewItem]:
        return [
            _item(r) for r in await self._query(f"SELECT {_RI} FROM review_item ORDER BY id", ())
        ]

    async def add_review_item(self, item: ReviewItem) -> int:
        def work(db: sqlite3.Connection) -> int:
            cur = db.execute(
                "INSERT INTO review_item (kind, group_id, value, score_when_listed, status, "
                "rule_id, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (item.kind, item.group_id, item.value, item.score_when_listed, item.status,
                 item.rule_id, _now()),
            )  # fmt: skip
            return int(cur.lastrowid or 0)

        return await self._write(work)

    async def set_status(
        self,
        item_id: int,
        status: ReviewStatus,
        *,
        expect: set[ReviewStatus],
        by: str | None = None,
        at: str | None = None,
        memory_ref: str | None = None,
        closed_ref: str | None = None,
        target: tuple[str, str, str] | None = None,
        score: float | None = None,
    ) -> ReviewItem:
        wanted = sorted(expect)
        etype, entity, key = target or (None, None, None)

        def work(db: sqlite3.Connection) -> ReviewItem:
            cur = db.execute(
                f"UPDATE review_item SET status = ?, "
                f"decided_by = COALESCE(?, decided_by), decided_at = COALESCE(?, decided_at), "
                f"memory_ref = COALESCE(?, memory_ref), closed_ref = COALESCE(?, closed_ref), "
                f"rule_entity_type = COALESCE(?, rule_entity_type), "
                f"rule_entity = COALESCE(?, rule_entity), rule_key = COALESCE(?, rule_key), "
                f"score_when_listed = COALESCE(?, score_when_listed) "
                f"WHERE id = ? AND status IN ({_marks(len(wanted))})",
                (
                    status,
                    by,
                    at,
                    memory_ref,
                    closed_ref,
                    etype,
                    entity,
                    key,
                    score,
                    item_id,
                    *wanted,
                ),
            )
            row = db.execute(f"SELECT {_RI} FROM review_item WHERE id = ?", (item_id,)).fetchone()
            if cur.rowcount == 0:
                raise PromotionStateError(item_id, row[5] if row else None)
            return _item(row)

        return await self._write(work)

    async def closed_rule_refs(self) -> frozenset[str]:
        rows = await self._query(
            "SELECT memory_ref, closed_ref FROM review_item "
            "WHERE kind = 'candidate' AND status = 'closed'",
            (),
        )
        return frozenset(ref for row in rows for ref in row if ref)
