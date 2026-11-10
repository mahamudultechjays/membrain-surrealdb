from app.domain.ports.promotion import ReviewItem, Statement
from app.domain.promotion import ScoredStatement, Weights, score
from app.services.promotion.review import plan_review, to_scored

W = Weights(1.0, 0.5)


def s(user: str, value: str, at: str) -> ScoredStatement:
    return ScoredStatement(user, 1, value, "for", at)


def plan(
    rows: list[ScoredStatement],
    items: list[ReviewItem],
    candidate_at: float = 3,
    flag_at: float = 2,
):  # type: ignore[no-untyped-def]
    return plan_review(
        score(rows, W, personal_rule_at=1.75), items, candidate_at=candidate_at, flag_at=flag_at
    )


def item(
    status: str,
    value: str = "30 days",
    score_: float = 3,
    kind: str = "candidate",
    iid: int = 1,
    rule_id: int | None = None,
) -> ReviewItem:
    return ReviewItem(kind, 1, value, score_, status, id=iid, rule_id=rule_id)  # type: ignore[arg-type]


def test_worked_example_lists_drops_and_relists() -> None:
    rows = [s("a", "30 days", "1"), s("b", "30 days", "2"), s("c", "30 days", "3")]
    ch = plan(rows, [])
    assert [(i.kind, i.value, i.score_when_listed, i.status) for i in ch.open] == [
        ("candidate", "30 days", 3, "open")
    ]
    listed = [item("open")]
    rows.append(s("d", "60 days", "4"))
    assert plan(rows, listed).drop == [1]
    dropped = [item("dropped")]
    rows.append(s("a", "30 days", "5"))
    ch = plan(rows, dropped)
    assert (ch.open, ch.drop) == ([], [])
    rows.append(s("e", "30 days", "6"))
    assert [i.value for i in plan(rows, dropped).open] == ["30 days"]


def test_open_candidate_is_not_listed_twice() -> None:
    rows = [s("a", "30 days", "1"), s("b", "30 days", "2"), s("c", "30 days", "3")]
    assert plan(rows, [item("open")]).open == []


def test_no_candidate_when_rule_already_active() -> None:
    rows = [s("a", "30 days", "1"), s("b", "30 days", "2"), s("c", "30 days", "3")]
    assert plan(rows, [item("active")]).open == []


def test_rejected_value_relists_only_above_old_score() -> None:
    rows = [s("a", "30 days", "1"), s("b", "30 days", "2"), s("c", "30 days", "3")]
    rejected = [item("rejected", score_=3)]
    assert plan(rows, rejected).open == []
    rows.append(s("d", "30 days", "4"))
    assert [i.score_when_listed for i in plan(rows, rejected).open] == [4]


def test_flag_opens_at_flag_at_once_per_rule() -> None:
    rows = [
        s("a", "30 days", "1"),
        s("b", "30 days", "2"),
        s("c", "30 days", "3"),
        s("d", "60 days", "4"),
        s("e", "60 days", "5"),
    ]
    rule = item("active", iid=5)
    (flag,) = [i for i in plan(rows, [rule]).open if i.kind == "flag"]
    assert (flag.rule_id, flag.value, flag.score_when_listed) == (5, "30 days", 2)
    assert [
        i
        for i in plan(rows, [rule, item("open", kind="flag", iid=6, rule_id=5, score_=2)]).open
        if i.kind == "flag"
    ] == []


def test_kept_flag_reopens_only_above_kept_score() -> None:
    rows = [
        s("a", "30 days", "1"),
        s("b", "30 days", "2"),
        s("c", "30 days", "3"),
        s("d", "60 days", "4"),
        s("e", "60 days", "5"),
    ]
    items = [item("active", iid=5), item("kept", kind="flag", iid=6, rule_id=5, score_=2)]
    assert [i for i in plan(rows, items).open if i.kind == "flag"] == []
    rows.append(s("f", "60 days", "6"))
    assert [i.score_when_listed for i in plan(rows, items).open if i.kind == "flag"] == [3]


def test_to_scored_skips_ungrouped_rows() -> None:
    base = {
        "user": "a", "scope": "s", "source": "chat", "text": "t",
        "entity": "e", "key": "k", "value": "v", "said_at": "1",
    }  # fmt: skip
    rows = [
        Statement(memory_ref="r1", group_id=1, norm_value="30 days", stance="for", **base),  # type: ignore[arg-type]
        Statement(memory_ref="r2", **base),  # type: ignore[arg-type]
    ]
    assert to_scored(rows) == [ScoredStatement("a", 1, "30 days", "for", "1")]
