"""VCT tagger: tag stored facts with their top 3 nodes and top 3 goals, no LLM.

Facts stay in Agent Memory; only fact ids and tags go to the FactTagRepository.
A run pages through the facts of the tagged scopes (TAGGER_SCOPES), newest first,
and for every fact not yet processed:
1. carries a person's tags over from the fact it superseded, if any;
2. recalls the fact's text against the node passages and the goal passages;
3. keeps the first 3 distinct ids of each and saves them as "auto".
Recall scores are rank positions, not similarity, so matches are kept by order.
Tags a person set are never replaced. The scope list is an allowlist: the
matcher scopes and lab scopes are never tagged, even when listed.
"""

import asyncio
import logging
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from app.domain.errors import (
    MemoryNotConfiguredError,
    MemoryUnavailableError,
    TaggerBusyError,
)
from app.domain.ports.fact_lister import FactLister, ListedFact
from app.domain.ports.fact_tags import FactTagRepository
from app.domain.ports.memory_recall import MemoryRecall
from app.domain.ports.passage_writer import PassageWriter
from app.domain.ports.scope_registry import ScopeRegistry
from app.domain.vct import VctGoal, VctMap

logger = logging.getLogger(__name__)

TAGGER_VERSION = "v1"
TOP = 3
_RECALL_K = 10
_RECALL_CONCURRENCY = 4  # 16 recalls at once timed out at the 30 s client limit
_SEED_CONCURRENCY = 8
_NODE_TAG = re.compile(r"VCT node \[([a-z0-9-]+)\]")
_GOAL_TAG = re.compile(r"VCT goal \[([a-z0-9-]+)\]")
NEVER_TAGGED = ("org/spreetail/vct", "org/spreetail/lab")


def goal_text(goal: VctGoal) -> str:
    """The passage stored for a goal; the [id] tag maps a recall hit back to it."""
    return f"VCT goal [{goal.id}] {goal.name}. {goal.description}."


def taggable(scopes: list[str]) -> list[str]:
    """The allowlist without matcher and lab scopes, cleaned, each once."""
    kept: dict[str, None] = {}
    for raw in scopes:
        scope = raw.strip().strip("/")
        if scope and not any(scope == n or scope.startswith(f"{n}/") for n in NEVER_TAGGED):
            kept.setdefault(scope)
    return list(kept)


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


@dataclass(slots=True)
class TaggerRun:
    started_at: str
    scopes: list[str]
    finished_at: str | None = None
    # Facts seen in the tagged scopes, and how many of them were new.
    listed: int = 0
    new: int = 0
    tagged: int = 0
    # User tags carried over from a superseded fact.
    carried: int = 0
    failed: int = 0
    # True when the run stopped at the per-run limit; the rest go next run.
    capped: bool = False
    error: str | None = None
    failures: list[str] = field(default_factory=list)


class TaggerService:
    def __init__(
        self,
        tags: FactTagRepository,
        lister: FactLister,
        recall: MemoryRecall,
        passages: PassageWriter,
        registry: ScopeRegistry,
        vct_map: VctMap,
        *,
        scopes: list[str],
        nodes_scope: str,
        goals_scope: str,
        version: str = TAGGER_VERSION,
        max_facts: int = 500,
        page_size: int = 200,
        max_pages: int = 50,
    ) -> None:
        self._tags = tags
        self._lister = lister
        self._recall = recall
        self._passages = passages
        self._registry = registry
        self.map = vct_map
        self.scopes = taggable(scopes)
        self._nodes_scope = nodes_scope.strip("/")
        self._goals_scope = goals_scope.strip("/")
        self.version = version
        self._max_facts = max_facts
        self._page_size = page_size
        self._max_pages = max_pages
        self._lock = asyncio.Lock()
        self._gate = asyncio.Semaphore(_RECALL_CONCURRENCY)
        self._task: asyncio.Task[TaggerRun | None] | None = None
        self.current: TaggerRun | None = None
        self.last: TaggerRun | None = None
        self.next_run_at: str | None = None

    @property
    def running(self) -> bool:
        return self._lock.locked() or (self._task is not None and not self._task.done())

    def start(self) -> bool:
        """Start a run in the background; False when one is already running."""
        if self.running:
            return False
        self._task = asyncio.create_task(self._quiet_run())
        return True

    async def run(self) -> TaggerRun:
        if self._lock.locked():
            raise TaggerBusyError
        async with self._lock:
            run = TaggerRun(started_at=_now(), scopes=list(self.scopes))
            self.current = run
            try:
                await self._tag_new(run)
            except (MemoryNotConfiguredError, MemoryUnavailableError) as exc:
                run.error = str(exc) or type(exc).__name__
                logger.warning("VCT tagger run stopped: %s", run.error)
            finally:
                run.finished_at = _now()
                self.current, self.last = None, run
            logger.info(
                "VCT tagger: listed=%d new=%d tagged=%d carried=%d failed=%d capped=%s",
                run.listed,
                run.new,
                run.tagged,
                run.carried,
                run.failed,
                run.capped,
            )
            return run

    async def loop(self, interval_seconds: float) -> None:
        """Run every `interval_seconds`, the first time after one interval."""
        while True:
            next_at = datetime.now(UTC) + timedelta(seconds=interval_seconds)
            self.next_run_at = next_at.isoformat(timespec="seconds")
            await asyncio.sleep(interval_seconds)
            await self._quiet_run()

    async def seed_goals(self, *, force: bool = False) -> int:
        """Store every goal as a passage in the goals scope, once."""
        if self._goals_scope in await self._registry.list(self._goals_scope) and not force:
            return 0
        await self._registry.ensure(self._goals_scope)
        gate = asyncio.Semaphore(_SEED_CONCURRENCY)

        async def write(goal: VctGoal) -> None:
            async with gate:
                await self._passages.write(goal_text(goal), self._goals_scope)

        await asyncio.gather(*(write(g) for g in self.map.goals))
        return len(self.map.goals)

    async def _quiet_run(self) -> TaggerRun | None:
        try:
            return await self.run()
        except TaggerBusyError:
            return None
        except Exception:
            logger.exception("VCT tagger run failed")
            return None

    async def _tag_new(self, run: TaggerRun) -> None:
        todo = await self._untagged(run)
        run.new = len(todo)
        await asyncio.gather(*(self._tag(fact, scope, run) for fact, scope in todo))

    async def _untagged(self, run: TaggerRun) -> list[tuple[ListedFact, str]]:
        """Facts in the tagged scopes the tagger has not handled, newest first."""
        todo: list[tuple[ListedFact, str]] = []
        cursor: str | None = None
        for _ in range(self._max_pages):
            page = await self._lister.page(self.scopes, limit=self._page_size, cursor=cursor)
            mine = [(f, s) for f in page.facts if (s := self._scope_of(f))]
            run.listed += len(mine)
            done = await self._tags.processed([f.id for f, _ in mine])
            for fact, scope in mine:
                if fact.id in done:
                    continue
                if len(todo) >= self._max_facts:
                    run.capped = True
                    return todo
                todo.append((fact, scope))
            cursor = page.cursor
            if cursor is None:
                break
        return todo

    def _scope_of(self, fact: ListedFact) -> str | None:
        return next((s for s in fact.scopes if s in self.scopes), None)

    async def _tag(self, fact: ListedFact, scope: str, run: TaggerRun) -> None:
        try:
            if fact.supersedes:
                run.carried += await self._tags.copy_user_tags(fact.supersedes, fact.id, scope)
            nodes, goals = await asyncio.gather(
                self._match(fact.text, self._nodes_scope, _NODE_TAG, self._is_node),
                self._match(fact.text, self._goals_scope, _GOAL_TAG, self._is_goal),
            )
            await self._tags.save_auto(
                fact.id, scope, nodes=nodes, goals=goals, version=self.version
            )
            run.tagged += 1
        except Exception as exc:
            run.failed += 1
            run.failures.append(fact.id)
            logger.warning("VCT tagger: fact %s failed: %s", fact.id, exc)

    async def _match(
        self, text: str, scope: str, pattern: re.Pattern[str], known: Callable[[str], bool]
    ) -> list[str]:
        if not text.strip():
            return []
        async with self._gate:
            result = await self._recall.recall(text, lens=scope, k=_RECALL_K)
        ids: dict[str, None] = {}
        for hit in result.hits:
            found = pattern.search(hit.text or "")
            if found and known(found.group(1)):
                ids.setdefault(found.group(1))
        return list(ids)[:TOP]

    def _is_node(self, node_id: str) -> bool:
        return self.map.node(node_id) is not None

    def _is_goal(self, goal_id: str) -> bool:
        return self.map.goal(goal_id) is not None
