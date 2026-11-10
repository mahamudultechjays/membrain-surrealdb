"""Review findings C1, C2, I1: decisions lock the item, close what was approved,
and remember the score at the time of the decision."""

import asyncio
from datetime import date

import pytest

from app.adapters.sqlite import SqlitePromotion
from app.domain.errors import PromotionStateError
from app.domain.ports.promotion import FactGroup, ReviewItem
from app.services.promotion import decisions
from app.services.promotion.review import ReviewChanges, apply_review

TODAY = date(2026, 11, 12)


class SlowWriter:
    def __init__(self, delay: float = 0.05) -> None:
        self.delay = delay
        self.calls: list[dict[str, object]] = []

    async def write(self, **kwargs: object) -> str:
        self.calls.append(kwargs)
        await asyncio.sleep(self.delay)
        return f"a{len(self.calls)}"


async def seed(repo: SqlitePromotion, value: str = "30 days") -> tuple[int, int]:
    gid = await repo.add_group(
        FactGroup("CR window", "cobalt ridge", "organization", "Cobalt Ridge", "return_window")
    )
    iid = await repo.add_review_item(ReviewItem("candidate", gid, value, 3, "open"))
    return gid, iid


async def test_approve_is_not_undone_by_a_drop_during_the_write() -> None:
    repo, writer = SqlitePromotion(":memory:"), SlowWriter()
    _, iid = await seed(repo)

    async def drop_soon() -> None:
        await asyncio.sleep(0.01)
        await apply_review(repo, ReviewChanges(drop=[iid]))

    item, _ = await asyncio.gather(
        decisions.approve(repo, writer, iid, by="a@x.com", edit=None), drop_soon()
    )
    assert (item.status, item.memory_ref) == ("active", "a1")
    assert [i.status for i in await repo.review_items()] == ["active"]


async def test_two_approvals_at_once_write_once() -> None:
    repo, writer = SqlitePromotion(":memory:"), SlowWriter()
    _, iid = await seed(repo)
    results = await asyncio.gather(
        decisions.approve(repo, writer, iid, by="a@x.com", edit=None),
        decisions.approve(repo, writer, iid, by="b@x.com", edit=None),
        return_exceptions=True,
    )
    assert sum(isinstance(r, PromotionStateError) for r in results) == 1
    assert len(writer.calls) == 1


async def test_close_writes_to_the_entity_and_key_approved() -> None:
    repo, writer = SqlitePromotion(":memory:"), SlowWriter(0)
    gid, iid = await seed(repo)
    await decisions.approve(repo, writer, iid, by="a@x.com", edit=None)
    await repo.update_rule(gid, label="x", entity_type="company", entity="Other", key="other_key")
    await decisions.close(repo, writer, iid, by="a@x.com", today=TODAY)
    closing = writer.calls[1]
    assert (closing["entity"], closing["key"]) == ("Cobalt Ridge", "return_window")


async def test_approve_refused_while_the_topic_has_an_active_rule() -> None:
    repo, writer = SqlitePromotion(":memory:"), SlowWriter(0)
    gid, iid = await seed(repo)
    await decisions.approve(repo, writer, iid, by="a@x.com", edit=None)
    other = await repo.add_review_item(ReviewItem("candidate", gid, "60 days", 3, "open"))
    with pytest.raises(PromotionStateError):
        await decisions.approve(repo, writer, other, by="a@x.com", edit=None)
    assert len(writer.calls) == 1


async def test_edit_is_not_saved_when_the_write_fails() -> None:
    class Failing:
        async def write(self, **kwargs: object) -> str:
            raise RuntimeError("down")

    repo = SqlitePromotion(":memory:")
    _, iid = await seed(repo)
    edit = decisions.RuleEdit("New", "company", "New Co", "new_key", "30 days")
    with pytest.raises(RuntimeError):
        await decisions.approve(repo, Failing(), iid, by="a@x.com", edit=edit)
    (group,) = await repo.groups()
    assert group.rule_key == "return_window"
    assert [i.status for i in await repo.review_items()] == ["open"]


async def test_reject_and_keep_record_the_score_at_decision() -> None:
    repo, writer = SqlitePromotion(":memory:"), SlowWriter(0)
    gid, iid = await seed(repo)
    rejected = await decisions.reject(repo, iid, by="a@x.com", score_now=4.0)
    assert rejected.score_when_listed == 4.0
    rule = await repo.add_review_item(ReviewItem("candidate", gid, "45 days", 3, "open"))
    await decisions.approve(repo, writer, rule, by="a@x.com", edit=None)
    flag = await repo.add_review_item(ReviewItem("flag", gid, "45 days", 2, "open", rule_id=rule))
    kept = await decisions.keep(repo, flag, by="a@x.com", score_now=2.5)
    assert kept.score_when_listed == 2.5
