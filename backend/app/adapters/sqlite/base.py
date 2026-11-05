"""Shared SQLite plumbing for the local stores in backend/data.

Each call opens its own connection in a worker thread, so the event loop never
blocks and no connection is shared across threads (":memory:" keeps one shared
connection instead, for tests).
"""

import asyncio
import sqlite3
from collections.abc import Callable
from pathlib import Path
from typing import Any


class SqliteStore:
    def __init__(self, path: str | Path, schema: str) -> None:
        self._path = str(path)
        self._shared: sqlite3.Connection | None = None
        if self._path == ":memory:":
            self._shared = sqlite3.connect(":memory:", check_same_thread=False)
        else:
            Path(self._path).parent.mkdir(parents=True, exist_ok=True)
        self._run(lambda db: db.executescript(schema))

    async def _query(self, sql: str, params: tuple[Any, ...]) -> list[tuple[Any, ...]]:
        return await asyncio.to_thread(self._run, lambda db: db.execute(sql, params).fetchall())

    async def _write[T](self, work: Callable[[sqlite3.Connection], T]) -> T:
        """Run `work` in one transaction, off the event loop."""
        return await asyncio.to_thread(self._run, work)

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
