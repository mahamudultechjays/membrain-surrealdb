from app.core.config import Settings
from app.domain.promotion import ScoredStatement, Weights, clean_subject, score, weight

W = Weights(1.0, 0.5)


def s(user: str, value: str, at: str, stance: str = "for", group: int = 1) -> ScoredStatement:
    return ScoredStatement(user, group, value, stance, at)  # type: ignore[arg-type]


def by_value(rows: list[ScoredStatement], at: float = 1.75) -> dict:
    return {(v.group_id, v.value): v for v in score(rows, W, personal_rule_at=at)}


def test_weight_halves_each_repeat() -> None:
    assert [weight(n, W) for n in (1, 2, 3)] == [1, 0.5, 0.25]


def test_worked_example_from_the_spec() -> None:
    rows = [s("a", "30 days", "1"), s("b", "30 days", "2"), s("c", "30 days", "3")]
    assert by_value(rows)[(1, "30 days")].team_score == 3
    rows.append(s("d", "60 days", "4"))
    v = by_value(rows)[(1, "30 days")]
    assert (v.for_score, v.against_score, v.team_score) == (3, 1, 2)
    rows.append(s("a", "30 days", "5"))
    v = by_value(rows)[(1, "30 days")]
    assert (v.for_score, v.team_score) == (3.5, 2.5)
    rows.append(s("e", "30 days", "6"))
    v = by_value(rows)[(1, "30 days")]
    assert (v.for_score, v.against_score, v.team_score) == (4.5, 1, 3.5)


def test_one_person_adds_at_most_about_two() -> None:
    rows = [s("a", "30 days", f"{i:02}") for i in range(10)]
    assert by_value(rows)[(1, "30 days")].team_score < 2


def test_personal_rule_at_third_statement_default_and_second_in_test_profile() -> None:
    rows = [s("a", "30 days", "t1"), s("a", "30 days", "t2"), s("a", "30 days", "t3")]
    assert by_value(rows, 1.75)[(1, "30 days")].personal_rule_since == {"a": "t3"}
    assert by_value(rows, 1.5)[(1, "30 days")].personal_rule_since == {"a": "t2"}


def test_opposing_values_count_against_each_other() -> None:
    v = by_value([s("a", "30 days", "1"), s("b", "60 days", "2")])
    assert v[(1, "30 days")].team_score == 0
    assert v[(1, "60 days")].team_score == 0


def test_explicit_against_counts_only_against_that_value() -> None:
    v = by_value([s("a", "30 days", "1"), s("b", "30 days", "2", "against")])
    assert v[(1, "30 days")].team_score == 0
    assert list(v) == [(1, "30 days")]


def test_values_compare_loosely_and_groups_stay_apart() -> None:
    v = by_value([s("a", "30 days", "1"), s("b", "30 Days.", "2"), s("c", "30 days", "3", group=2)])
    assert v[(1, "30 days")].for_score == 2
    assert v[(1, "30 days")].holders == ("a", "b")
    assert v[(2, "30 days")].for_score == 1


def test_clean_subject() -> None:
    assert clean_subject("organisation/Cobalt_Ridge") == "cobalt ridge"
    assert clean_subject("  Cobalt   Ridge ") == "cobalt ridge"


def test_generic_subjects_setting_is_split_and_lowercased() -> None:
    assert Settings(PROMOTION_GENERIC_SUBJECTS="Spreetail, We").promotion_generic_subjects() == {
        "spreetail",
        "we",
    }


def test_extra_value_without_holders_gets_its_against_score() -> None:
    # Everyone moved from the active rule's 30 days to 60 days (finding I2).
    rows = [s("a", "60 days", "1"), s("b", "60 days", "2")]
    v = {
        (x.group_id, x.value): x
        for x in score(rows, W, personal_rule_at=1.75, extra=[(1, "30 days")])
    }
    assert (v[(1, "30 days")].against_score, v[(1, "30 days")].holders) == (2, ())


def test_evidence_lists_people_for_and_against_with_weights() -> None:
    from app.domain.promotion import EvidenceRow, evidence

    rows = [
        s("a", "30 days", "1"),
        s("b", "30 days", "2"),
        s("a", "30 days", "3"),
        s("d", "60 days", "4"),
        s("e", "30 days", "5", "against"),
    ]
    found_for, found_against = evidence(rows, 1, "30 days", W)
    assert found_for == [
        EvidenceRow("a", (1.0, 0.5), ("1", "3"), "30 days", ("", "")),
        EvidenceRow("b", (1.0,), ("2",), "30 days", ("",)),
    ]
    assert found_against == [
        EvidenceRow("d", (1.0,), ("4",), "60 days", ("",)),
        EvidenceRow("e", (1.0,), ("5",), "not 30 days", ("",)),
    ]
