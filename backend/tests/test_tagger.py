import asyncio
import time
from collections.abc import Iterator
from typing import ClassVar

import pytest
from fastapi.testclient import TestClient

from app.adapters.sqlite import SqliteFactTags
from app.composition import get_tagger_service
from app.domain.errors import MemoryNotConfiguredError, MemoryUnavailableError, TaggerBusyError
from app.domain.ports.fact_lister import ListedFact, ListedPage
from app.domain.ports.memory_recall import RecallHit, RecallResult
from app.main import app
from app.services import vct_map
from app.services.access import AccessService
from app.services.onboarding import node_text
from app.services.tagger import TaggerService, goal_text, taggable
from tests.conftest import FakeRegistry, sign_in

ME = "org/spreetail/user/mahamudul_hasan"
OTHER = "org/spreetail/user/arun"
NODES = "org/spreetail/vct/nodes"
GOALS = "org/spreetail/vct/goals"
VMAP = vct_map.load()


class FakeLister:
    """Serves the given pages in order, one per call, as the listing would."""

    def __init__(self, pages: list[list[ListedFact]]) -> None:
        self.pages = pages
        self.calls: list[tuple[list[str], str | None]] = []
        self.error: Exception | None = None

    async def page(self, scopes: list[str], *, limit: int, cursor: str | None) -> ListedPage:
        self.calls.append((scopes, cursor))
        if self.error:
            raise self.error
        if not self.pages:
            return ListedPage()
        index = int(cursor or 0)
        more = index + 1 < len(self.pages)
        return ListedPage(self.pages[index], str(index + 1) if more else None)


class FakeRecall:
    """Answers with node or goal passages by trigger word, depending on the lens."""

    ROUTES: ClassVar[dict[str, tuple[list[str], list[str]]]] = {
        "freight": (["sc6", "sc6", "zz9", "sc7", "mo1", "sc4"], ["ff-mgmt5", "ff-mgmt3"]),
        "payout": (["mo1", "fi4"], ["ps-mgmt5"]),
    }

    def __init__(self) -> None:
        self.queries: list[tuple[str, str]] = []
        self.fail_on: str | None = None

    async def recall(self, query: str, *, lens: str, k: int) -> RecallResult:
        self.queries.append((query, lens))
        if self.fail_on and self.fail_on in query:
            raise MemoryUnavailableError("timeout")
        nodes, goals = next((v for w, v in self.ROUTES.items() if w in query), ([], []))
        if lens == NODES:
            texts = [node_text(n) if (n := VMAP.node(i)) else f"VCT node [{i}] ?" for i in nodes]
        else:
            texts = [goal_text(g) for i in goals if (g := VMAP.goal(i))]
        hits = [RecallHit(f"p{n}", t, "chunk", 0.38) for n, t in enumerate(texts)]
        return RecallResult(hits=hits)


class FakePassages:
    def __init__(self) -> None:
        self.written: list[tuple[str, str]] = []

    async def write(self, text: str, scope: str) -> None:
        self.written.append((text, scope))


def _fact(fact_id: str, text: str, scope: str = ME, supersedes: str | None = None) -> ListedFact:
    return ListedFact(fact_id, text, (scope,), supersedes)


def _service(
    lister: FakeLister,
    recall: FakeRecall | None = None,
    tags: SqliteFactTags | None = None,
    max_facts: int = 500,
) -> TaggerService:
    return TaggerService(
        tags or SqliteFactTags(":memory:"),
        lister,
        recall or FakeRecall(),
        FakePassages(),
        FakeRegistry(),
        VMAP,
        scopes=[ME, f" {ME}/ ", "org/spreetail/vct/nodes", "org/spreetail/lab/x"],
        nodes_scope=NODES,
        goals_scope=GOALS,
        max_facts=max_facts,
    )


def test_matcher_and_lab_scopes_are_never_tagged() -> None:
    assert taggable([ME, f"/{ME}/", "org/spreetail/vct", "org/spreetail/lab/a", " "]) == [ME]
    assert taggable(["org/spreetail/vctx"]) == ["org/spreetail/vctx"]


async def test_a_run_tags_new_facts_in_the_tagged_scopes_only() -> None:
    tags = SqliteFactTags(":memory:")
    lister = FakeLister(
        [
            [_fact("f1", "UPS freight rate up 5.9%"), _fact("x1", "freight", OTHER)],
            [_fact("f2", "Walmart payout delay 14 days"), _fact("f3", "Team lunch on Friday")],
        ]
    )
    service = _service(lister, tags=tags)

    run = await service.run()
    again = await service.run()

    assert lister.calls[0] == ([ME], None)
    assert (run.listed, run.new, run.tagged, run.failed, run.capped) == (3, 3, 3, 0, False)
    assert run.finished_at
    assert run.error is None
    found = await tags.tags_for(["f1", "f2", "f3", "x1"])
    assert [(t.kind, t.tag, t.rank) for t in found["f1"]] == [
        ("goal", "ff-mgmt5", 1),
        ("goal", "ff-mgmt3", 2),
        ("node", "sc6", 1),  # the repeated sc6 and the unknown zz9 are dropped
        ("node", "sc7", 2),
        ("node", "mo1", 3),
    ]
    assert {t.tagger_version for t in found["f1"]} == {"v1"}
    assert "f3" not in found  # nothing matched, but it is processed
    assert await tags.processed(["f3", "x1"]) == {"f3"}
    assert (again.new, again.tagged) == (0, 0)
    assert service.last is again
    assert service.current is None


async def test_user_tags_follow_a_superseded_fact() -> None:
    tags = SqliteFactTags(":memory:")
    await tags.save_auto("old", ME, nodes=["sc6"], goals=["ff-mgmt5"], version="v1")
    await tags.set_tag("old", "node", "fi4", "mahamudul")
    service = _service(FakeLister([[_fact("new", "freight up", supersedes="old")]]), tags=tags)

    run = await service.run()

    assert run.carried == 1
    view = [(t.kind, t.tag, t.source) for t in (await tags.tags_for(["new"]))["new"]]
    assert ("node", "fi4", "user") in view
    assert ("goal", "ff-mgmt5", "auto") in view


async def test_a_capped_run_leaves_the_rest_for_the_next_run() -> None:
    pages = [[_fact("f1", "freight"), _fact("f2", "payout")], [_fact("f3", "freight")]]
    service = _service(FakeLister(pages), max_facts=2)

    first = await service.run()
    second = await service.run()

    assert (first.tagged, first.capped) == (2, True)
    assert (second.tagged, second.capped) == (1, False)


async def test_a_failing_fact_is_counted_and_retried_next_run() -> None:
    recall = FakeRecall()
    recall.fail_on = "payout"
    lister = FakeLister([[_fact("f1", "freight"), _fact("f2", "payout")]])
    service = _service(lister, recall)

    first = await service.run()
    recall.fail_on = None
    second = await service.run()

    assert (first.tagged, first.failed, first.failures) == (1, 1, ["f2"])
    assert (second.new, second.tagged) == (1, 1)


async def test_memory_errors_end_the_run_with_an_error() -> None:
    lister = FakeLister([[]])
    lister.error = MemoryNotConfiguredError("missing")

    run = await _service(lister).run()

    assert run.error == "missing"
    assert run.finished_at is not None


async def test_empty_text_is_processed_without_recall() -> None:
    recall = FakeRecall()
    tags = SqliteFactTags(":memory:")

    run = await _service(FakeLister([[_fact("f1", "  ")]]), recall, tags).run()

    assert run.tagged == 1
    assert recall.queries == []
    assert await tags.processed(["f1"]) == {"f1"}


async def test_only_one_run_at_a_time() -> None:
    gate = asyncio.Event()

    class SlowLister(FakeLister):
        async def page(self, scopes: list[str], *, limit: int, cursor: str | None) -> ListedPage:
            await gate.wait()
            return ListedPage()

    service = _service(SlowLister([]))
    assert service.start() is True
    await asyncio.sleep(0)

    assert service.running
    assert service.start() is False
    with pytest.raises(TaggerBusyError):
        await service.run()
    gate.set()
    await asyncio.sleep(0.01)
    assert not service.running
    assert service.last is not None


async def test_the_loop_runs_on_its_interval_and_survives_errors() -> None:
    lister = FakeLister([])
    service = _service(lister)

    async def boom(run: object) -> None:
        raise RuntimeError("bug")

    task = asyncio.create_task(service.loop(0.01))
    await asyncio.sleep(0.05)
    calls = len(lister.calls)
    service._tag_new = boom  # type: ignore[method-assign]
    await asyncio.sleep(0.03)
    task.cancel()

    assert calls >= 2
    assert service.next_run_at is not None


async def test_goals_are_seeded_once() -> None:
    passages = FakePassages()
    registry = FakeRegistry()
    service = TaggerService(
        SqliteFactTags(":memory:"),
        FakeLister([]),
        FakeRecall(),
        passages,
        registry,
        VMAP,
        scopes=[ME],
        nodes_scope=NODES,
        goals_scope=GOALS,
    )

    first = await service.seed_goals()
    again = await service.seed_goals()
    forced = await service.seed_goals(force=True)

    assert (first, again, forced) == (42, 0, 42)
    assert registry.ensured == [GOALS, GOALS]
    assert passages.written[0] == (goal_text(VMAP.goals[0]), GOALS)


@pytest.fixture
def service() -> TaggerService:
    return _service(FakeLister([[_fact("f1", "freight")]]))


@pytest.fixture
def client(access: AccessService, service: TaggerService) -> Iterator[TestClient]:
    app.dependency_overrides[get_tagger_service] = lambda: service
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def test_admin_runs_the_tagger_and_reads_its_status(client: TestClient) -> None:
    sign_in(client, "admin@x.com", "Ada Admin")

    before = client.get("/api/v1/admin/vct/tagger").json()
    started = client.post("/api/v1/admin/vct/tagger/run")
    status = client.get("/api/v1/admin/vct/tagger").json()
    for _ in range(100):
        if status["last"]:
            break
        time.sleep(0.02)
        status = client.get("/api/v1/admin/vct/tagger").json()

    assert before["scopes"] == [ME]
    assert before["last"] is None
    assert before["version"] == "v1"
    assert before["interval_hours"] == 3.0
    assert started.status_code == 202
    assert status["running"] is False
    assert status["last"]["tagged"] == 1


def test_a_second_run_while_running_is_409(client: TestClient, service: TaggerService) -> None:
    sign_in(client, "admin@x.com", "Ada Admin")
    service.start = lambda: False  # type: ignore[method-assign]

    assert client.post("/api/v1/admin/vct/tagger/run").status_code == 409


def test_tagger_routes_refuse_non_admins(client: TestClient) -> None:
    sign_in(client, "priya@x.com", "Priya")

    assert client.get("/api/v1/admin/vct/tagger").status_code == 403
    assert client.post("/api/v1/admin/vct/tagger/run").status_code == 403
