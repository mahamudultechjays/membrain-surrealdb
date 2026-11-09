"""VCT tagger: tag stored facts with their top 3 nodes and top 3 goals, no LLM.

Facts stay in Agent Memory; only fact ids and tags go to the FactTagRepository.
A run pages through the facts of the tagged scopes (TAGGER_SCOPES), newest first,
and for every fact not yet processed:
1. carries a person's tags over from the fact it superseded, if any;
2. recalls the fact's text against the node passages and the goal passages;
3. keeps the first 3 distinct ids of each and saves them as "auto".
Recall scores are rank positions, not similarity, so matches are kept by order
and there is no score threshold. Instead the node scope also holds a few
"not business" decoy passages (DECOYS): when one ranks first, the fact is
marked not business and gets no node or goal (decoy test, 9 Nov: 0 of 33
business facts dropped). Tags a person set are never replaced. The scope list is an allowlist: the
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
from app.services.onboarding import node_text

logger = logging.getLogger(__name__)

TAGGER_VERSION = "v1"
TOP = 3
_RECALL_K = 10
_RECALL_CONCURRENCY = 4  # 16 recalls at once timed out at the 30 s client limit
_SEED_CONCURRENCY = 8
_NODE_TAG = re.compile(r"VCT (node|none) \[([a-z0-9-]+)\]")
_GOAL_TAG = re.compile(r"VCT (goal) \[([a-z0-9-]+)\]")
# What _match returns when a decoy ranks first.
NOT_BUSINESS = "<not-business>"
NEVER_TAGGED = ("org/spreetail/vct", "org/spreetail/lab")

# Generic "not business" passages stored beside the nodes. Kept broad on purpose:
# they are not tuned to one dataset.
DECOYS: dict[str, str] = {
    "dev": "Software engineering work: code, commits, commit messages, branches, pull "
    "requests, pushed, uncommitted, tests passing, frontend, backend, localhost, bugs, "
    "deployments, servers, latency, versions, phases, status of a build.",
    "api": "Apps and their APIs: endpoints, routes, URLs, pages, tabs, screens, buttons, "
    "checkboxes, output formats, purposes of a feature, how a tool behaves.",
    "tools": "Files and links: artifacts, documents, PDFs, HTML pages, downloads folder, "
    "file locations, page counts, drafts, write-ups.",
    "memory": "The memory system itself: Agent Memory, recall, chat, reflect, consolidate, "
    "elaborate, scopes, layers, lab runs, fact counts, attribute and relation counts, "
    "extraction, Membrain.",
    "account": "Accounts and access: emails, passwords, API keys, permissions, access "
    "levels, admin rights, login, user names, display names.",
    "people": "People and the team: who collaborates with whom, assigned tasks, standups, "
    "meetings, proposals and opinions about the project, preferences of a person.",
    "personal": "Personal life and small talk: lunch, work from home days, favourite "
    "things, hobbies, weather, travel, sports, news, birthdays, holidays.",
    # Added 9 Nov: project notes the others missed fell on mo1.
    "projects": "Project notes and tests: test runs, test profiles, question counts, "
    "findings, write-ups, design options, app locations, jobs and intervals, settings "
    "and configuration of internal tools.",
}


def decoy_text(key: str, description: str) -> str:
    """A decoy passage; "VCT none [key]" ranking first means not business."""
    return f"VCT none [{key}] {description}"


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
    # Of the tagged facts, how many a decoy marked "not business".
    not_business: int = 0
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
        # The exact passage texts that count; older wordings stored in Agent
        # Memory are ignored, since passages there can't be edited.
        self._current = (
            {node_text(n) for n in vct_map.nodes}
            | {goal_text(g) for g in vct_map.goals}
            | {decoy_text(k, d) for k, d in DECOYS.items()}
        )
        self._task: asyncio.Task[TaggerRun | None] | None = None
        self.current: TaggerRun | None = None
        self.last: TaggerRun | None = None
        self.next_run_at: str | None = None

    @property
    def running(self) -> bool:
        return self._lock.locked() or (self._task is not None and not self._task.done())

    def start(self, *, retag: bool = False) -> bool:
        """Start a run in the background; False when one is already running.

        `retag` re-tags every fact in the tagged scopes, not only new ones;
        tags a person set still stay.
        """
        if self.running:
            return False
        self._task = asyncio.create_task(self._quiet_run(retag=retag))
        return True

    async def run(self, *, retag: bool = False) -> TaggerRun:
        if self._lock.locked():
            raise TaggerBusyError
        async with self._lock:
            run = TaggerRun(started_at=_now(), scopes=list(self.scopes))
            self.current = run
            try:
                await self._tag_new(run, retag=retag)
            except (MemoryNotConfiguredError, MemoryUnavailableError) as exc:
                run.error = str(exc) or type(exc).__name__
                logger.warning("VCT tagger run stopped: %s", run.error)
            finally:
                run.finished_at = _now()
                self.current, self.last = None, run
            logger.info(
                "VCT tagger: listed=%d new=%d tagged=%d not_business=%d carried=%d failed=%d "
                "capped=%s",
                run.listed,
                run.new,
                run.tagged,
                run.not_business,
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

    async def seed_decoys(self, only: list[str] | None = None) -> int:
        """Store the "not business" decoys (or just `only`) in the node scope.
        Writing one twice is harmless: matching keeps each id once."""
        await self._registry.ensure(self._nodes_scope)
        keys = [k for k in DECOYS if only is None or k in only]
        await asyncio.gather(
            *(self._passages.write(decoy_text(k, DECOYS[k]), self._nodes_scope) for k in keys)
        )
        return len(keys)

    async def refresh_nodes(self, node_ids: list[str]) -> int:
        """Store the current passage of these nodes after a wording change; the
        old passage stays in Agent Memory but no longer counts."""
        nodes = [n for i in node_ids if (n := self.map.node(i))]
        await asyncio.gather(
            *(self._passages.write(node_text(n), self._nodes_scope) for n in nodes)
        )
        return len(nodes)

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

    async def _quiet_run(self, *, retag: bool = False) -> TaggerRun | None:
        try:
            return await self.run(retag=retag)
        except TaggerBusyError:
            return None
        except Exception:
            logger.exception("VCT tagger run failed")
            return None

    async def _tag_new(self, run: TaggerRun, *, retag: bool = False) -> None:
        todo = await self._untagged(run, retag=retag)
        run.new = len(todo)
        await asyncio.gather(*(self._tag(fact, scope, run) for fact, scope in todo))

    async def _untagged(
        self, run: TaggerRun, *, retag: bool = False
    ) -> list[tuple[ListedFact, str]]:
        """Facts in the tagged scopes the tagger has not handled (all of them
        with `retag`), newest first."""
        todo: list[tuple[ListedFact, str]] = []
        cursor: str | None = None
        for _ in range(self._max_pages):
            page = await self._lister.page(self.scopes, limit=self._page_size, cursor=cursor)
            mine = [(f, s) for f in page.facts if (s := self._scope_of(f))]
            run.listed += len(mine)
            await self._tags.link_turns([(f.id, f.turn_id, s) for f, s in mine if f.turn_id])
            done = set() if retag else await self._tags.processed([f.id for f, _ in mine])
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
            business = not nodes or nodes[0] != NOT_BUSINESS
            await self._tags.save_auto(
                fact.id,
                scope,
                nodes=[n for n in nodes if n != NOT_BUSINESS],
                goals=goals,
                version=self.version,
                business=business,
            )
            run.tagged += 1
            run.not_business += 0 if business else 1
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
            result = await self._recall.recall(text, lenses=[scope], k=_RECALL_K)
        ids: dict[str, None] = {}
        decoy_first = False
        for hit in result.hits:
            found = pattern.search(hit.text or "")
            if not found or (hit.text or "").strip() not in self._current:
                continue
            if found.group(1) == "none":
                # A decoy only matters when it ranks above every real match; the
                # real matches below it are still kept, as guesses.
                decoy_first = decoy_first or not ids
                continue
            tag = found.group(found.lastindex or 1)
            if known(tag):
                ids.setdefault(tag)
        return ([NOT_BUSINESS] if decoy_first else []) + list(ids)[:TOP]

    def _is_node(self, node_id: str) -> bool:
        return self.map.node(node_id) is not None

    def _is_goal(self, goal_id: str) -> bool:
        return self.map.goal(goal_id) is not None
