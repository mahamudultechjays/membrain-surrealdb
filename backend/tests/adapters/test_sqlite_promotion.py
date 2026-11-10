import pytest

from app.adapters.sqlite import SqlitePromotion
from app.domain.errors import PromotionStateError
from app.domain.ports.promotion import FactGroup, ReviewItem, Statement


def st(ref: str, scope: str = "s", user: str = "a@s.com") -> Statement:
    return Statement(
        user, scope, ref, "chat", "t", "Cobalt Ridge", "return_window", "30 days", "2026-11-10"
    )


def group(subject: str = "cobalt ridge") -> FactGroup:
    return FactGroup(
        "Cobalt Ridge return window", subject, "organization", "Cobalt Ridge", "return_window"
    )


async def test_add_statements_skips_known_refs() -> None:
    db = SqlitePromotion(":memory:")
    assert await db.add_statements([st("f1")]) == 1
    assert await db.add_statements([st("f1"), st("f2")]) == 1
    assert await db.known_refs(["f1", "f2", "f3"]) == {"f1", "f2"}


async def test_mark_replaced_and_live_refs() -> None:
    db = SqlitePromotion(":memory:")
    await db.add_statements([st("f1"), st("f2"), st("g1", scope="other")])
    assert await db.mark_replaced(["f1"], "now") == 1
    assert await db.mark_replaced(["f1"], "later") == 0
    assert await db.live_refs(["s"]) == {"f2"}
    gid = await db.add_group(group())
    rows = await db.unprocessed(10)
    assert [r.memory_ref for r in rows] == ["f2", "g1"]
    await db.set_grouping([(r.id, gid, "30 days", "for") for r in rows if r.id], "now")
    assert {r.memory_ref for r in await db.counted()} == {"f2", "g1"}


async def test_unprocessed_then_set_grouping() -> None:
    db = SqlitePromotion(":memory:")
    await db.add_statements([st("f1")])
    gid = await db.add_group(group())
    (row,) = await db.unprocessed(5)
    assert row.id is not None
    await db.set_grouping([(row.id, gid, "30 days", "against")], "now")
    assert await db.unprocessed(5) == []
    (done,) = await db.counted()
    assert (done.group_id, done.norm_value, done.stance, done.processed_at) == (
        gid,
        "30 days",
        "against",
        "now",
    )


async def test_groups_for_subjects_matches_aliases() -> None:
    db = SqlitePromotion(":memory:")
    gid = await db.add_group(group())
    await db.add_alias(gid, "cobalt ridge returns")
    await db.add_alias(gid, "cobalt ridge returns")
    await db.add_alias(gid, "cobalt ridge")
    (found,) = await db.groups_for_subjects({"cobalt ridge returns"})
    assert found.id == gid and found.aliases == ("cobalt ridge returns",)
    assert await db.groups_for_subjects({"northwind"}) == []


async def test_update_rule() -> None:
    db = SqlitePromotion(":memory:")
    gid = await db.add_group(group())
    await db.update_rule(gid, label="Returns", entity_type="org", entity="Cobalt", key="returns")
    (g,) = await db.groups()
    assert (g.label, g.rule_entity_type, g.rule_entity, g.rule_key) == (
        "Returns",
        "org",
        "Cobalt",
        "returns",
    )


async def test_set_status_guards_expected_status() -> None:
    db = SqlitePromotion(":memory:")
    iid = await db.add_review_item(ReviewItem("candidate", 1, "30 days", 3.0, "open"))
    item = await db.set_status(
        iid, "active", expect={"open"}, by="x@s.com", at="now", memory_ref="a1"
    )
    assert (item.status, item.decided_by, item.memory_ref) == ("active", "x@s.com", "a1")
    with pytest.raises(PromotionStateError):
        await db.set_status(iid, "active", expect={"open"})
    with pytest.raises(PromotionStateError):
        await db.set_status(999, "active", expect={"open"})


async def test_closed_rule_refs() -> None:
    db = SqlitePromotion(":memory:")
    iid = await db.add_review_item(ReviewItem("candidate", 1, "30 days", 3.0, "open"))
    await db.set_status(iid, "active", expect={"open"}, memory_ref="a1")
    assert await db.closed_rule_refs() == frozenset()
    await db.set_status(iid, "closed", expect={"active"}, closed_ref="a2")
    assert await db.closed_rule_refs() == frozenset({"a1", "a2"})
    assert [i.status for i in await db.review_items()] == ["closed"]
