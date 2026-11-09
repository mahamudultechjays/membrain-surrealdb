"""FactTagRepository on the same local SQLite file as the scope grants.

Three tables, none holding fact text:
- tagged_facts: one row per fact the tagger has handled, with its scope;
- fact_tags: the tags, one row per fact, kind and tag;
- tag_feedback: every edit a person makes, insert only.
Each user edit changes fact_tags and writes tag_feedback in one transaction.
"""

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from app.adapters.sqlite.base import SqliteStore
from app.domain.errors import FactNotTaggedError
from app.domain.ports.fact_tags import FactTag, FeedbackStats, TagAction, TagCount, TagKind

_SCHEMA = """
CREATE TABLE IF NOT EXISTS tagged_facts (
    fact_id        TEXT PRIMARY KEY,
    scope          TEXT NOT NULL,
    tagger_version TEXT NOT NULL,
    tagged_at      TEXT NOT NULL,
    business       INTEGER NOT NULL DEFAULT 1
);
CREATE INDEX IF NOT EXISTS tagged_facts_scope ON tagged_facts (scope, tagged_at);
CREATE TABLE IF NOT EXISTS fact_tags (
    fact_id        TEXT NOT NULL,
    scope          TEXT NOT NULL,
    kind           TEXT NOT NULL CHECK (kind IN ('node', 'goal')),
    tag            TEXT NOT NULL,
    rank           INTEGER NOT NULL CHECK (rank BETWEEN 1 AND 3),
    source         TEXT NOT NULL CHECK (source IN ('auto', 'user')),
    tagger_version TEXT,
    updated_by     TEXT NOT NULL,
    updated_at     TEXT NOT NULL,
    PRIMARY KEY (fact_id, kind, tag)
);
CREATE INDEX IF NOT EXISTS fact_tags_filter ON fact_tags (kind, tag, rank);
CREATE INDEX IF NOT EXISTS fact_tags_scope ON fact_tags (scope);
CREATE TABLE IF NOT EXISTS tag_feedback (
    fact_id        TEXT NOT NULL,
    kind           TEXT NOT NULL CHECK (kind IN ('node', 'goal')),
    action         TEXT NOT NULL CHECK (action IN ('add', 'change', 'remove', 'accept')),
    old            TEXT,
    new            TEXT,
    tagger_version TEXT,
    user           TEXT NOT NULL,
    at             TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS tag_feedback_at ON tag_feedback (at);
"""

_TAGGER = "tagger"
_COLUMNS = "fact_id, scope, kind, tag, rank, source, tagger_version, updated_by, updated_at"


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _marks(values: list[str]) -> str:
    return ",".join("?" * len(values))


def _top(db: sqlite3.Connection, fact_id: str, kind: TagKind) -> tuple[str, str | None] | None:
    """The rank 1 tag of this kind and the tagger version that set it."""
    row = db.execute(
        "SELECT tag, tagger_version FROM fact_tags WHERE fact_id = ? AND kind = ? AND rank = 1",
        (fact_id, kind),
    ).fetchone()
    return (row[0], row[1]) if row else None


def _scope(db: sqlite3.Connection, fact_id: str) -> str:
    row = db.execute("SELECT scope FROM tagged_facts WHERE fact_id = ?", (fact_id,)).fetchone()
    if row is None:
        raise FactNotTaggedError(fact_id)
    return str(row[0])


def _log(
    db: sqlite3.Connection,
    fact_id: str,
    kind: TagKind,
    action: TagAction,
    old: str | None,
    new: str | None,
    version: str | None,
    user: str,
) -> None:
    db.execute(
        "INSERT INTO tag_feedback (fact_id, kind, action, old, new, tagger_version, user, at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (fact_id, kind, action, old, new, version, user, _now()),
    )


def _accept(db: sqlite3.Connection, fact_id: str, kind: TagKind, user: str) -> None:
    top = _top(db, fact_id, kind)
    if top is None:
        return
    db.execute(
        "UPDATE fact_tags SET source = 'user', updated_by = ?, updated_at = ? "
        "WHERE fact_id = ? AND kind = ? AND rank = 1",
        (user, _now(), fact_id, kind),
    )
    _log(db, fact_id, kind, "accept", top[0], top[0], top[1], user)


def _add_business_column(db: sqlite3.Connection) -> None:
    """Files made before 9 Nov lack tagged_facts.business; every fact counted as business."""
    columns = {row[1] for row in db.execute("PRAGMA table_info(tagged_facts)")}
    if "business" not in columns:
        db.execute("ALTER TABLE tagged_facts ADD COLUMN business INTEGER NOT NULL DEFAULT 1")


class SqliteFactTags(SqliteStore):
    def __init__(self, path: str | Path) -> None:
        super().__init__(path, _SCHEMA)
        self._run(_add_business_column)

    async def tags_for(self, fact_ids: list[str]) -> dict[str, list[FactTag]]:
        if not fact_ids:
            return {}
        rows = await self._query(
            f"SELECT {_COLUMNS} FROM fact_tags WHERE fact_id IN ({_marks(fact_ids)}) "
            "ORDER BY fact_id, kind, rank",
            tuple(fact_ids),
        )
        found: dict[str, list[FactTag]] = {}
        for row in rows:
            found.setdefault(row[0], []).append(FactTag(*row))
        return found

    async def processed(self, fact_ids: list[str]) -> set[str]:
        if not fact_ids:
            return set()
        rows = await self._query(
            f"SELECT fact_id FROM tagged_facts WHERE fact_id IN ({_marks(fact_ids)})",
            tuple(fact_ids),
        )
        return {row[0] for row in rows}

    async def not_business(self, fact_ids: list[str]) -> set[str]:
        if not fact_ids:
            return set()
        rows = await self._query(
            "SELECT fact_id FROM tagged_facts "
            f"WHERE business = 0 AND fact_id IN ({_marks(fact_ids)})",
            tuple(fact_ids),
        )
        return {row[0] for row in rows}

    async def scope_of(self, fact_id: str) -> str | None:
        rows = await self._query("SELECT scope FROM tagged_facts WHERE fact_id = ?", (fact_id,))
        return str(rows[0][0]) if rows else None

    async def save_auto(
        self,
        fact_id: str,
        scope: str,
        *,
        nodes: list[str],
        goals: list[str],
        version: str,
        business: bool = True,
    ) -> None:
        now = _now()
        if not business:
            nodes, goals = [], []

        def work(db: sqlite3.Connection) -> None:
            # A person's tag means it is business, whatever the tagger thinks.
            has_user = db.execute(
                "SELECT 1 FROM fact_tags WHERE fact_id = ? AND source = 'user'", (fact_id,)
            ).fetchone()
            db.execute(
                "INSERT INTO tagged_facts (fact_id, scope, tagger_version, tagged_at, business) "
                "VALUES (?, ?, ?, ?, ?) ON CONFLICT (fact_id) DO UPDATE SET "
                "scope = excluded.scope, tagger_version = excluded.tagger_version, "
                "tagged_at = excluded.tagged_at, business = excluded.business",
                (fact_id, scope, version, now, int(business or bool(has_user))),
            )
            for kind, tags in (("node", nodes), ("goal", goals)):
                user_set = db.execute(
                    "SELECT 1 FROM fact_tags WHERE fact_id = ? AND kind = ? AND source = 'user'",
                    (fact_id, kind),
                ).fetchone()
                if user_set:
                    continue
                db.execute("DELETE FROM fact_tags WHERE fact_id = ? AND kind = ?", (fact_id, kind))
                ranked = list(dict.fromkeys(tags))[:3]
                db.executemany(
                    f"INSERT INTO fact_tags ({_COLUMNS}) VALUES (?, ?, ?, ?, ?, 'auto', ?, ?, ?)",
                    [
                        (fact_id, scope, kind, tag, rank, version, _TAGGER, now)
                        for rank, tag in enumerate(ranked, start=1)
                    ],
                )

        await self._write(work)

    async def copy_user_tags(self, old_fact_id: str, new_fact_id: str, scope: str) -> int:
        now = _now()

        def work(db: sqlite3.Connection) -> int:
            rows = db.execute(
                "SELECT kind, tag, rank, updated_by FROM fact_tags "
                "WHERE fact_id = ? AND source = 'user'",
                (old_fact_id,),
            ).fetchall()
            for kind in {row[0] for row in rows}:
                db.execute(
                    "DELETE FROM fact_tags WHERE fact_id = ? AND kind = ?", (new_fact_id, kind)
                )
            db.executemany(
                f"INSERT INTO fact_tags ({_COLUMNS}) VALUES (?, ?, ?, ?, ?, 'user', NULL, ?, ?)",
                [(new_fact_id, scope, k, t, r, by, now) for k, t, r, by in rows],
            )
            return len(rows)

        return await self._write(work)

    async def set_tag(self, fact_id: str, kind: TagKind, tag: str, user: str) -> None:
        def work(db: sqlite3.Connection) -> None:
            scope = _scope(db, fact_id)
            top = _top(db, fact_id, kind)
            old, version = top if top else (None, None)
            if old == tag:
                _accept(db, fact_id, kind, user)
                return
            db.execute("DELETE FROM fact_tags WHERE fact_id = ? AND kind = ?", (fact_id, kind))
            db.execute(
                f"INSERT INTO fact_tags ({_COLUMNS}) VALUES (?, ?, ?, ?, 1, 'user', NULL, ?, ?)",
                (fact_id, scope, kind, tag, user, _now()),
            )
            db.execute("UPDATE tagged_facts SET business = 1 WHERE fact_id = ?", (fact_id,))
            _log(db, fact_id, kind, "change" if old else "add", old, tag, version, user)

        await self._write(work)

    async def remove(self, fact_id: str, kind: TagKind, user: str) -> None:
        def work(db: sqlite3.Connection) -> None:
            _scope(db, fact_id)
            top = _top(db, fact_id, kind)
            if top is None:
                return
            db.execute("DELETE FROM fact_tags WHERE fact_id = ? AND kind = ?", (fact_id, kind))
            _log(db, fact_id, kind, "remove", top[0], None, top[1], user)

        await self._write(work)

    async def accept(self, fact_id: str, kind: TagKind, user: str) -> None:
        def work(db: sqlite3.Connection) -> None:
            _scope(db, fact_id)
            _accept(db, fact_id, kind, user)

        await self._write(work)

    async def counts(self, scopes: list[str]) -> list[TagCount]:
        if not scopes:
            return []
        rows = await self._query(
            "SELECT kind, tag, COUNT(*) FROM fact_tags "
            f"WHERE rank = 1 AND scope IN ({_marks(scopes)}) GROUP BY kind, tag ORDER BY kind, tag",
            tuple(scopes),
        )
        return [TagCount(kind, tag, n) for kind, tag, n in rows]

    async def totals(self, scopes: list[str]) -> tuple[int, int, int]:
        if not scopes:
            return (0, 0, 0)
        rows = await self._query(
            "SELECT COUNT(*), COALESCE(SUM(t.business = 1 AND NOT EXISTS ("
            "SELECT 1 FROM fact_tags f WHERE f.fact_id = t.fact_id AND f.kind = 'goal')), 0), "
            "COALESCE(SUM(t.business = 0), 0) "
            f"FROM tagged_facts t WHERE t.scope IN ({_marks(scopes)})",
            tuple(scopes),
        )
        return (int(rows[0][0]), int(rows[0][1]), int(rows[0][2]))

    async def without(self, kind: TagKind, scopes: list[str], limit: int, offset: int) -> list[str]:
        if not scopes:
            return []
        rows = await self._query(
            "SELECT t.fact_id FROM tagged_facts t "
            f"WHERE t.scope IN ({_marks(scopes)}) AND t.business = 1 AND NOT EXISTS ("
            "SELECT 1 FROM fact_tags f WHERE f.fact_id = t.fact_id AND f.kind = ?) "
            "ORDER BY t.tagged_at DESC, t.fact_id LIMIT ? OFFSET ?",
            (*scopes, kind, limit, offset),
        )
        return [row[0] for row in rows]

    async def feedback_stats(self, since: str) -> FeedbackStats:
        # A correction is a change or removal of a tag the tagger set.
        corrected = "action IN ('change', 'remove') AND tagger_version IS NOT NULL"
        totals = await self._query(
            f"SELECT COUNT(*), COALESCE(SUM({corrected}), 0) FROM tag_feedback WHERE at >= ?",
            (since,),
        )
        pairs = await self._query(
            "SELECT old, new, COUNT(*) AS n FROM tag_feedback "
            f"WHERE at >= ? AND {corrected} GROUP BY old, new ORDER BY n DESC, old LIMIT 5",
            (since,),
        )
        edits, corrections = totals[0]
        return FeedbackStats(
            edits=edits, corrections=corrections, confusions=[(o, n, c) for o, n, c in pairs]
        )
