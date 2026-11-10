from app.adapters.sqlite import SqlitePromotion
from app.domain.errors import GroupingModelError
from app.domain.ports.grouping_model import NewTopic, StatementIn, TopicIn, TopicMatch
from app.domain.ports.promotion import FactGroup, Statement
from app.services.promotion.grouping import group_new

GENERIC = frozenset({"spreetail", "we"})


def st(ref: str, entity: str = "cobalt_ridge", value: str = "30 days") -> Statement:
    return Statement(
        "a@s.com", "s", ref, "chat", f"text {ref}", entity, "return_window", value, ref
    )


class Model:
    """Answers from a function of (statement, topics, allow_new); records calls."""

    def __init__(self, answer, error: Exception | None = None) -> None:  # type: ignore[no-untyped-def]
        self.answer = answer
        self.error = error
        self.calls: list[tuple[list[str], list[int], bool]] = []

    async def match(
        self, statements: list[StatementIn], topics: list[TopicIn], *, allow_new: bool
    ) -> list[TopicMatch]:
        self.calls.append(([s.ref for s in statements], [t.id for t in topics], allow_new))
        if self.error:
            raise self.error
        return [m for s in statements if (m := self.answer(s, topics, allow_new))]


def new(label: str = "Cobalt Ridge return window") -> NewTopic:
    return NewTopic(label, "organization", "Cobalt Ridge", "return_window")


async def run(db: SqlitePromotion, model: Model) -> object:
    return await group_new(db, model, batch_size=10, generic_subjects=GENERIC, now="now")


async def ids(db: SqlitePromotion) -> dict[int, str]:
    return {s.id: s.memory_ref for s in await db.unprocessed(50) if s.id}


async def test_conflict_notes_land_in_one_group_with_three_values() -> None:
    db = SqlitePromotion(":memory:")
    await db.add_statements(
        [st("f1", value="30 days"), st("f2", value="45 days"), st("f3", value="60 days")]
    )

    def answer(s: StatementIn, topics: list[TopicIn], allow_new: bool) -> TopicMatch:
        if topics:
            return TopicMatch(s.ref, topics[0].id, None, s.value, "for")
        return TopicMatch(s.ref, None, new(), s.value, "for")

    await run(db, Model(answer))
    rows = await db.counted()
    assert len({r.group_id for r in rows}) == 1
    assert sorted(r.norm_value or "" for r in rows) == ["30 days", "45 days", "60 days"]
    assert len(await db.groups()) == 1


async def test_same_subject_pass_runs_before_full_list() -> None:
    db = SqlitePromotion(":memory:")
    gid = await db.add_group(FactGroup("CR window", "cobalt ridge", "org", "Cobalt Ridge", "rw"))
    await db.add_group(FactGroup("Other", "northwind", "org", "Northwind", "x"))
    await db.add_statements([st("f1")])
    model = Model(lambda s, t, a: TopicMatch(s.ref, gid, None, s.value, "for"))
    stats = await run(db, model)
    assert len(model.calls) == 1
    assert model.calls[0][1:] == ([gid], False)
    assert stats.first_pass == 1  # type: ignore[attr-defined]


async def test_unmatched_go_to_full_list_and_may_create_topic() -> None:
    db = SqlitePromotion(":memory:")
    gid = await db.add_group(FactGroup("CR window", "cobalt ridge", "org", "Cobalt Ridge", "rw"))
    other = await db.add_group(FactGroup("Other", "northwind", "org", "Northwind", "x"))
    await db.add_statements([st("f1")])

    def answer(s: StatementIn, topics: list[TopicIn], allow_new: bool) -> TopicMatch | None:
        return (
            TopicMatch(s.ref, None, new("CR restocking fee"), s.value, "for") if allow_new else None
        )

    model = Model(answer)
    stats = await run(db, model)
    assert [c[1:] for c in model.calls] == [([gid], False), ([gid, other], True)]
    assert stats.new_topics == 1 and stats.full_list == 1  # type: ignore[attr-defined]


async def test_generic_subject_skips_first_pass() -> None:
    db = SqlitePromotion(":memory:")
    await db.add_group(FactGroup("Spreetail PTO", "spreetail", "org", "Spreetail", "pto"))
    await db.add_statements([st("f1", entity="Spreetail")])
    model = Model(lambda s, t, a: TopicMatch(s.ref, t[0].id, None, s.value, "for"))
    await run(db, model)
    assert [c[2] for c in model.calls] == [True]


async def test_cross_subject_match_learns_alias() -> None:
    db = SqlitePromotion(":memory:")
    gid = await db.add_group(FactGroup("CR window", "cobalt ridge", "org", "Cobalt Ridge", "rw"))
    await db.add_statements([st("f1", entity="cobalt_ridge_returns")])
    model = Model(lambda s, t, a: TopicMatch(s.ref, gid, None, s.value, "for") if a else None)
    stats = await run(db, model)
    assert stats.aliases == 1  # type: ignore[attr-defined]
    (g,) = await db.groups()
    assert g.aliases == ("cobalt ridge returns",)
    await db.add_statements([st("f2", entity="cobalt_ridge_returns")])
    model2 = Model(lambda s, t, a: TopicMatch(s.ref, gid, None, s.value, "for"))
    await run(db, model2)
    assert [c[2] for c in model2.calls] == [False]


async def test_same_new_label_in_one_batch_creates_one_topic() -> None:
    db = SqlitePromotion(":memory:")
    await db.add_statements([st("f1"), st("f2")])
    await run(db, Model(lambda s, t, a: TopicMatch(s.ref, None, new("CR window"), s.value, "for")))
    assert len(await db.groups()) == 1
    assert len({r.group_id for r in await db.counted()}) == 1


async def test_new_topic_refused_in_first_pass() -> None:
    db = SqlitePromotion(":memory:")
    await db.add_group(FactGroup("CR window", "cobalt ridge", "org", "Cobalt Ridge", "rw"))
    await db.add_statements([st("f1")])
    model = Model(
        lambda s, t, a: TopicMatch(s.ref, None, new("Sneaky"), s.value, "for") if not a else None
    )
    stats = await run(db, model)
    assert len(await db.groups()) == 1
    assert stats.left == 1  # type: ignore[attr-defined]


async def test_bad_model_answers_leave_statements_unprocessed() -> None:
    db = SqlitePromotion(":memory:")
    await db.add_statements([st("f1"), st("f2"), st("f3")])

    def answer(s: StatementIn, topics: list[TopicIn], allow_new: bool) -> TopicMatch | None:
        if s.text.endswith("f1"):
            return TopicMatch("nope", None, new(), s.value, "for")  # unknown ref
        if s.text.endswith("f2"):
            return TopicMatch(s.ref, 999, None, s.value, "for")  # unknown topic
        return None  # omitted

    stats = await run(db, Model(answer))
    assert stats.left == 3  # type: ignore[attr-defined]
    assert len(await db.unprocessed(10)) == 3

    stats = await run(db, Model(answer, error=GroupingModelError("down")))
    assert stats.error == "down"  # type: ignore[attr-defined]
    assert len(await db.unprocessed(10)) == 3


async def test_new_topics_for_the_same_entity_and_key_in_one_batch_merge() -> None:
    # Live run 10 Nov: "minimum order quantity" and "minimum order quantity for POs".
    db = SqlitePromotion(":memory:")
    await db.add_statements(
        [st("f1", entity="pinecrest_kitchenware"), st("f2", entity="pinecrest_kitchenware")]
    )
    labels = iter(["Pinecrest minimum order quantity", "Pinecrest minimum order quantity for POs"])

    def answer(s: StatementIn, topics: list[TopicIn], allow_new: bool) -> TopicMatch:
        topic = NewTopic(
            next(labels), "organization", "Pinecrest Kitchenware", "minimum_order_quantity"
        )
        return TopicMatch(s.ref, None, topic, "500 units", "for")

    await run(db, Model(answer))
    assert [g.label for g in await db.groups()] == ["Pinecrest minimum order quantity"]
    assert len({r.group_id for r in await db.counted()}) == 1
