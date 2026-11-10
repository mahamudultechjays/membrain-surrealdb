from app.adapters.sqlite import SqlitePromotion
from app.domain.ports.fact_lister import ListedFact, ListedPage
from app.domain.ports.user_scopes import ScopeGrant
from app.services.promotion.intake import intake, personal_owners

ANA, BEN = "org/spreetail/user/ana", "org/spreetail/user/ben"
OWNERS = {ANA: "ana@s.com", BEN: "ben@s.com"}


def fact(fid: str, scope: str, kind: str = "turn", supersedes: str | None = None) -> ListedFact:
    return ListedFact(
        id=fid, text=f"text {fid}", scopes=(scope,), supersedes=supersedes,
        entity_type="organisation", entity="cobalt_ridge", key="return_window",
        value="30 days", created_at=f"2026-11-10T00:00:{fid[-1]}0", source_kind=kind,
    )  # fmt: skip


class Lister:
    def __init__(self, *pages: list[ListedFact], more: bool = False) -> None:
        self.pages = list(pages)
        self.more = more

    async def page(self, scopes: list[str], *, limit: int, cursor: str | None) -> ListedPage:
        i = int(cursor or 0)
        last = i + 1 >= len(self.pages) and not self.more
        return ListedPage(
            self.pages[i] if i < len(self.pages) else [], None if last else str(i + 1)
        )


def test_personal_owners_keeps_personal_layer_only() -> None:
    grants = [
        ScopeGrant("ana@s.com", "Ana", ANA, "write", "personal"),
        ScopeGrant("ana@s.com", "Ana", "org/spreetail", "read", "org"),
    ]
    assert personal_owners(grants) == {ANA: "ana@s.com"}


async def test_chat_and_app_facts_become_statements_for_the_owner() -> None:
    db = SqlitePromotion(":memory:")
    stats = await intake(
        db, Lister([fact("f1", ANA, "turn"), fact("f2", BEN, "upsert")]), OWNERS, now="n"
    )
    assert (stats.listed, stats.new) == (2, 2)
    rows = {r.memory_ref: r for r in await db.unprocessed(10)}
    assert (rows["f1"].user, rows["f1"].source, rows["f1"].entity) == (
        "ana@s.com",
        "chat",
        "cobalt_ridge",
    )
    assert (rows["f2"].user, rows["f2"].source) == ("ben@s.com", "app")


async def test_consolidated_and_foreign_scope_facts_are_skipped() -> None:
    db = SqlitePromotion(":memory:")
    stats = await intake(
        db, Lister([fact("f1", ANA, "consolidation"), fact("f2", "org/spreetail")]), OWNERS, now="n"
    )
    assert (stats.new, stats.skipped) == (0, 2)


async def test_second_run_adds_nothing_new() -> None:
    db = SqlitePromotion(":memory:")
    lister = Lister([fact("f1", ANA)])
    await intake(db, lister, OWNERS, now="n")
    assert (await intake(db, lister, OWNERS, now="n")).new == 0


async def test_correction_marks_old_statement_replaced() -> None:
    db = SqlitePromotion(":memory:")
    await intake(db, Lister([fact("f1", ANA)]), OWNERS, now="n")
    stats = await intake(db, Lister([fact("f2", ANA, supersedes="f1")]), OWNERS, now="n2")
    assert stats.replaced == 1
    assert [r.memory_ref for r in await db.unprocessed(10)] == ["f2"]


async def test_removed_fact_is_marked_replaced() -> None:
    db = SqlitePromotion(":memory:")
    await intake(db, Lister([fact("f1", ANA), fact("f2", ANA)]), OWNERS, now="n")
    await intake(db, Lister([fact("f2", ANA)]), OWNERS, now="n2")
    assert await db.live_refs([ANA]) == {"f2"}


async def test_capped_listing_marks_nothing_removed() -> None:
    db = SqlitePromotion(":memory:")
    await intake(db, Lister([fact("f1", ANA)]), OWNERS, now="n")
    stats = await intake(db, Lister([fact("f2", ANA)], more=True), OWNERS, now="n2", max_pages=1)
    assert stats.capped is True
    assert await db.live_refs([ANA]) == {"f1", "f2"}


async def test_fact_seen_again_is_revived() -> None:
    db = SqlitePromotion(":memory:")
    await intake(db, Lister([fact("f1", ANA)]), OWNERS, now="n")
    await intake(db, Lister([]), OWNERS, now="n2")  # a short listing marks f1 removed
    assert await db.live_refs([ANA]) == set()
    stats = await intake(db, Lister([fact("f1", ANA)]), OWNERS, now="n3")
    assert await db.live_refs([ANA]) == {"f1"}
    assert stats.new == 0


async def test_statements_of_a_person_without_a_personal_scope_stop_counting() -> None:
    db = SqlitePromotion(":memory:")
    await intake(db, Lister([fact("f1", ANA), fact("f2", BEN)]), OWNERS, now="n")
    await intake(db, Lister([fact("f2", BEN)]), {BEN: "ben@s.com"}, now="n2")
    assert await db.live_refs([ANA, BEN]) == {"f2"}
