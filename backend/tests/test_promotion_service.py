import asyncio

import pytest

from app.adapters.sqlite import SqlitePromotion
from app.domain.errors import GroupingModelError, MemoryUnavailableError, PromotionBusyError
from app.domain.ports.fact_lister import ListedFact, ListedPage
from app.domain.ports.grouping_model import NewTopic, StatementIn, TopicIn, TopicMatch
from app.domain.ports.user_scopes import ScopeGrant
from app.domain.promotion import Weights
from app.services.promotion.service import PromotionService

USERS = ["ana", "ben", "cy"]


def grants() -> list[ScopeGrant]:
    return [
        ScopeGrant(f"{u}@s.com", u, f"org/spreetail/user/{u}", "write", "personal") for u in USERS
    ]


class Grants:
    async def all_grants(self) -> list[ScopeGrant]:
        return grants()


class Lister:
    def __init__(self, error: Exception | None = None, users: list[str] = USERS) -> None:
        self.error = error
        self.users = users

    async def page(self, scopes: list[str], *, limit: int, cursor: str | None) -> ListedPage:
        if self.error:
            raise self.error
        facts = [
            ListedFact(
                id=f"f{i}", text="Cobalt Ridge return window is 30 days",
                scopes=(f"org/spreetail/user/{u}",), entity_type="organisation",
                entity="cobalt_ridge", key="return_window", value="30 days",
                created_at=f"2026-11-10T00:0{i}", source_kind="turn",
            )
            for i, u in enumerate(self.users)
        ]  # fmt: skip
        return ListedPage(facts, None)


class Model:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error

    async def match(
        self, statements: list[StatementIn], topics: list[TopicIn], *, allow_new: bool
    ) -> list[TopicMatch]:
        if self.error:
            raise self.error
        new = NewTopic(
            "Cobalt Ridge return window", "organization", "Cobalt Ridge", "return_window"
        )
        return [
            TopicMatch(
                s.ref, topics[0].id if topics else None, None if topics else new, s.value, "for"
            )
            for s in statements
        ]


def service(
    db: SqlitePromotion, lister: Lister | None = None, model: Model | None = None
) -> PromotionService:
    return PromotionService(
        db, lister or Lister(), model or Model(), Grants(),  # type: ignore[arg-type]
        weights=Weights(1, 0.5), personal_rule_at=1.5, candidate_at=2, flag_at=1,
        batch_size=5, generic_subjects=frozenset({"spreetail"}),
    )  # fmt: skip


async def test_run_goes_from_listing_to_open_candidate() -> None:
    db = SqlitePromotion(":memory:")
    run = await service(db).run()
    assert (run.intake.new, run.opened, run.error) == (3, 1, None)
    (item,) = await db.review_items()
    assert (item.kind, item.value, item.status, item.score_when_listed) == (
        "candidate",
        "30 days",
        "open",
        3,
    )


async def test_second_run_while_running_is_busy() -> None:
    svc = service(SqlitePromotion(":memory:"))
    async with svc._lock:
        with pytest.raises(PromotionBusyError):
            await svc.run()
        assert svc.start() is False
    assert svc.start() is True
    await asyncio.sleep(0.05)


async def test_listing_failure_is_recorded_not_raised() -> None:
    db = SqlitePromotion(":memory:")
    run = await service(db, lister=Lister(MemoryUnavailableError("down"))).run()
    assert run.error == "down"
    assert await db.unprocessed(10) == []


async def test_grouping_failure_still_rescores() -> None:
    db = SqlitePromotion(":memory:")
    await service(db).run()
    more = Lister(users=[*USERS, "ana"])  # a fourth fact, still to group
    run = await service(db, lister=more, model=Model(GroupingModelError("no key"))).run()
    assert run.error == "no key"
    assert len(await db.unprocessed(10)) == 1
    assert [i.status for i in await db.review_items()] == ["open"]
