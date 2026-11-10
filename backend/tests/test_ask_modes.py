"""Ask modes: parsing hit text, finding conflicts across scopes, and best_match."""

import pytest

from app.domain.ports.memory_recall import RecallHit, RecallResult
from app.domain.ports.user_scopes import ScopeGrant
from app.services import ask_modes
from app.services.ask_modes.points import key_words, parse

ORG, OPS, ME = "org/spreetail", "org/spreetail/team/ops", "org/spreetail/user/arun_das"
GRANTS = [
    ScopeGrant("a@x.com", "Arun Das", ORG, "read", "org"),
    ScopeGrant("a@x.com", "Arun Das", OPS, "read", "team"),
    ScopeGrant("a@x.com", "Arun Das", ME, "write", "personal"),
]


class FakeRecall:
    def __init__(self, by_lens: dict[str, list[RecallHit]]) -> None:
        self.by_lens = by_lens

    async def recall(self, query: str, *, lens: str, k: int) -> RecallResult:
        return RecallResult(hits=self.by_lens.get(lens, []), tier="hybrid")


def _attr(hit_id: str, text: str, score: float) -> RecallHit:
    return RecallHit(hit_id, text, "attribute", score)


def _window(org: float, team: float, me: float) -> FakeRecall:
    return FakeRecall(
        {
            ORG: [_attr("o", "Cobalt Ridge's return window is 30 days", org)],
            OPS: [_attr("t", "Cobalt Ridge's return window is 45 days", team)],
            ME: [_attr("p", "Cobalt Ridge's returns window is 60 days", me)],
        }
    )


async def _run(mode: ask_modes.AskMode, recall: FakeRecall) -> ask_modes.ModeAnswer:
    return await ask_modes.run(mode, recall, GRANTS, q="return window?", tie_margin=0.10)


# --- parsing -----------------------------------------------------------------


def test_parses_the_live_attribute_shape() -> None:
    parsed = parse(
        _attr(
            "a",
            "Cobalt Ridge's return policy is within 30 days of delivery for a full refund",
            0.7,
        )
    )
    assert parsed is not None
    assert (parsed.entity, parsed.key) == ("Cobalt Ridge", "return policy")
    assert parsed.value == "within 30 days of delivery for a full refund"


def test_parses_the_mock_shape_and_skips_passages_and_entities() -> None:
    parsed = parse(_attr("a", "Acme · lead_time_days = 18", 0.5))
    assert parsed is not None and parsed.value == "18"
    assert parse(RecallHit("e", "Cobalt Ridge", "entity", 0.4)) is None
    assert parse(RecallHit("m", "Cobalt Ridge's window is 45 days", "memory_chunk", 1)) is None


def test_key_words_fold_plurals_and_synonyms_but_not_rewording() -> None:
    assert key_words("returns window") == key_words("return_window")
    assert key_words("max promotional discount") == key_words("maximum promotional discount")
    assert key_words("warranty_periods") == key_words("warranty period")
    assert key_words("return policy") != key_words("returns window")  # known gap
    assert key_words("gross") == {"gross"}


# --- default and by_layer ------------------------------------------------------


async def test_default_compares_nothing() -> None:
    result = await _run("default", _window(0.7, 0.7, 0.7))
    assert result.mode == "default"
    assert result.conflicts == [] and result.verdicts == {}
    assert sum(len(layer.hits) for layer in result.answer.layers) == 3


async def test_by_layer_flags_the_disagreement_without_choosing() -> None:
    result = await _run("by_layer", _window(0.7, 0.68, 0.72))
    [conflict] = result.conflicts
    assert conflict.id == "c1"
    assert (conflict.entity, conflict.winner_hit_id, result.verdicts) == ("Cobalt Ridge", None, {})
    assert [(v.value, v.layers) for v in conflict.values] == [
        ("60 days", ["personal"]),
        ("30 days", ["org"]),
        ("45 days", ["team"]),
    ]


async def test_matching_entities_by_subset_catches_renamed_lines() -> None:
    recall = FakeRecall(
        {
            ORG: [_attr("o", "Harbor Basics's maximum promotional discount is 10%", 0.5)],
            ME: [_attr("p", "Harbor Basics commodity line's max promotional discount is 12%", 0.4)],
        }
    )
    result = await _run("by_layer", recall)
    assert len(result.conflicts) == 1


async def test_reworded_keys_are_a_known_miss() -> None:
    recall = FakeRecall(
        {
            ORG: [_attr("o", "Cobalt Ridge's return policy is 30 days", 0.7)],
            ME: [_attr("p", "Cobalt Ridge's returns window is 60 days", 0.7)],
        }
    )
    assert (await _run("by_layer", recall)).conflicts == []


async def test_two_values_in_one_scope_are_history_not_a_conflict() -> None:
    recall = FakeRecall(
        {
            OPS: [
                _attr("t1", "Sable Kettle's safety stock is 200 units", 0.6),
                _attr("t2", "Sable Kettle line's safety stock is 250 units", 0.6),
            ]
        }
    )
    assert (await _run("by_layer", recall)).conflicts == []


async def test_same_value_everywhere_is_no_conflict() -> None:
    recall = FakeRecall(
        {
            ORG: [_attr("o", "Atlas Rug's shipping carrier is Acme Freight", 0.6)],
            ME: [_attr("p", "Atlas Rug's shipping carrier is acme freight.", 0.6)],
        }
    )
    assert (await _run("by_layer", recall)).conflicts == []


# --- best_match ---------------------------------------------------------------


async def test_best_match_near_tie_goes_to_the_broader_layer() -> None:
    result = await _run("best_match", _window(0.78, 0.74, 0.81))
    [conflict] = result.conflicts
    assert conflict.winner_hit_id == "o"
    assert conflict.reason == "Scores within 0.10, so the broader Org layer wins"
    assert result.verdicts["o"].status == "used"
    assert result.verdicts["p"].status == "set_aside"
    assert result.verdicts["p"].reason == "Disagrees with the chosen Org value: 30 days"
    assert result.verdicts["t"].status == "set_aside"


async def test_best_match_clear_lead_wins_even_from_personal() -> None:
    result = await _run("best_match", _window(0.60, 0.55, 0.95))
    [conflict] = result.conflicts
    assert conflict.winner_hit_id == "p"
    assert conflict.reason == "Closest match to the question (0.95 vs 0.60)"
    assert result.verdicts["o"].status == "set_aside"


async def test_best_match_team_wins_a_tie_when_org_is_silent() -> None:
    recall = FakeRecall(
        {
            OPS: [_attr("t", "Orca Blender's reorder point is 500 units", 0.60)],
            ME: [_attr("p", "Orca Blender's reorder point is 350 units", 0.65)],
        }
    )
    result = await _run("best_match", recall)
    assert result.conflicts[0].winner_hit_id == "t"


async def test_best_match_marks_agreeing_hits_as_used() -> None:
    recall = FakeRecall(
        {
            ORG: [_attr("o", "Cobalt Ridge's return window is 30 days", 0.7)],
            OPS: [_attr("t", "Cobalt Ridge's return window is 30 days", 0.7)],
            ME: [_attr("p", "Cobalt Ridge's return window is 60 days", 0.7)],
        }
    )
    result = await _run("best_match", recall)
    assert result.verdicts["t"].status == "used"
    assert result.verdicts["t"].reason == "Agrees with the chosen value"
    assert result.verdicts["p"].status == "set_aside"


async def test_best_match_same_layer_tie_goes_to_the_higher_score() -> None:
    other = "org/spreetail/team/eng"
    grants = [*GRANTS, ScopeGrant("a@x.com", "Arun Das", other, "read", "team")]
    recall = FakeRecall(
        {
            OPS: [_attr("t1", "Kodiak Cooler's warranty period is 12 months", 0.60)],
            other: [_attr("t2", "Kodiak Cooler's warranty periods is 24 months", 0.65)],
        }
    )
    result = await ask_modes.run("best_match", recall, grants, q="warranty?", tie_margin=0.1)
    assert result.conflicts[0].winner_hit_id == "t2"


@pytest.mark.parametrize(
    ("requested", "expected"),
    [(None, ("by_layer", "config")), ("best_match", ("best_match", "request"))],
)
def test_resolve_mode(requested: ask_modes.AskMode | None, expected: tuple[str, str]) -> None:
    assert ask_modes.resolve_mode(requested, "by_layer") == expected


async def test_conflicts_below_the_relevance_floor_are_not_flagged() -> None:
    # Agent Memory's rank filler: every record of a small scope, scored 0.38 and down.
    filler = _window(0.374, 0.368, 0.362)
    for mode in ("by_layer", "best_match"):
        result = await ask_modes.run(
            mode, filler, GRANTS, q="wifi password?", tie_margin=0.10, min_score=0.40
        )
        assert result.conflicts == []
        assert result.verdicts == {}


async def test_one_relevant_value_is_enough_to_flag_the_conflict() -> None:
    result = await ask_modes.run(
        "by_layer", _window(0.50, 0.36, 0.35), GRANTS, q="window?", tie_margin=0.1, min_score=0.4
    )
    assert len(result.conflicts) == 1
