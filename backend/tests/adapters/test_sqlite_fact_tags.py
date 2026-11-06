from pathlib import Path

import pytest

from app.adapters.sqlite import SqliteFactTags, SqliteUserScopes
from app.domain.errors import FactNotTaggedError
from app.domain.ports.fact_tags import FactTag

ME = "org/spreetail/user/mahamudul_hasan"
OTHER = "org/spreetail/user/arun"
EPOCH = "2000-01-01"


async def _tagged(repo: SqliteFactTags, fact_id: str = "f1", scope: str = ME) -> None:
    await repo.save_auto(
        fact_id, scope, nodes=["sc6", "sc7", "mo1"], goals=["ff-mgmt5", "ff-mgmt3"], version="v1"
    )


def _view(tags: list[FactTag]) -> list[tuple[str, str, int, str]]:
    return [(t.kind, t.tag, t.rank, t.source) for t in tags]


async def _tags(repo: SqliteFactTags, fact_id: str = "f1") -> list[FactTag]:
    return (await repo.tags_for([fact_id]))[fact_id]


async def test_save_auto_keeps_three_ranked_tags_on_a_shared_file(tmp_path: Path) -> None:
    db = tmp_path / "data" / "user_scopes.db"
    SqliteUserScopes(db)  # all local stores share one file
    repo = SqliteFactTags(db)

    nodes = ["sc6", "sc6", "sc7", "mo1", "sc4"]  # a repeat, and one past the top 3
    await repo.save_auto("f1", ME, nodes=nodes, goals=[], version="v1")

    tags = await _tags(repo)
    assert _view(tags) == [
        ("node", "sc6", 1, "auto"),
        ("node", "sc7", 2, "auto"),
        ("node", "mo1", 3, "auto"),
    ]
    assert tags[0].tagger_version == "v1"
    assert tags[0].updated_by == "tagger"
    assert await repo.processed(["f1", "f2"]) == {"f1"}
    assert await repo.scope_of("f1") == ME
    assert await repo.scope_of("f2") is None
    assert await repo.tags_for([]) == {}
    assert await repo.processed([]) == set()


async def test_retagging_replaces_auto_tags_but_never_a_persons() -> None:
    repo = SqliteFactTags(":memory:")
    await _tagged(repo)
    await repo.set_tag("f1", "node", "fi4", "mahamudul")

    await repo.save_auto("f1", ME, nodes=["sc1"], goals=["src-mgmt1"], version="v2")

    assert _view(await _tags(repo)) == [
        ("goal", "src-mgmt1", 1, "auto"),
        ("node", "fi4", 1, "user"),
    ]


async def test_change_makes_the_new_tag_rank_one_and_logs_a_correction() -> None:
    repo = SqliteFactTags(":memory:")
    await _tagged(repo)

    await repo.set_tag("f1", "node", "fi4", "mahamudul")

    nodes = [t for t in await _tags(repo) if t.kind == "node"]
    assert _view(nodes) == [("node", "fi4", 1, "user")]
    assert nodes[0].updated_by == "mahamudul"
    assert nodes[0].tagger_version is None
    stats = await repo.feedback_stats(EPOCH)
    assert (stats.edits, stats.corrections, stats.confusions) == (1, 1, [("sc6", "fi4", 1)])


async def test_picking_the_current_tag_counts_as_accept() -> None:
    repo = SqliteFactTags(":memory:")
    await _tagged(repo)

    await repo.set_tag("f1", "goal", "ff-mgmt5", "arun")
    await repo.accept("f1", "node", "arun")

    view = _view(await _tags(repo))
    assert ("goal", "ff-mgmt5", 1, "user") in view
    assert ("goal", "ff-mgmt3", 2, "auto") in view  # alternatives stay
    assert ("node", "sc6", 1, "user") in view
    stats = await repo.feedback_stats(EPOCH)
    assert (stats.edits, stats.corrections) == (2, 0)


async def test_remove_drops_the_kind_and_the_fact_stays_processed() -> None:
    repo = SqliteFactTags(":memory:")
    await _tagged(repo)

    await repo.remove("f1", "goal", "mahamudul")
    await repo.remove("f1", "goal", "mahamudul")  # nothing left: no second log row

    assert {t.kind for t in await _tags(repo)} == {"node"}
    assert await repo.processed(["f1"]) == {"f1"}
    assert await repo.without("goal", [ME], limit=10, offset=0) == ["f1"]
    assert (await repo.feedback_stats(EPOCH)).confusions == [("ff-mgmt5", None, 1)]


async def test_a_person_adds_a_tag_to_a_kind_with_none() -> None:
    repo = SqliteFactTags(":memory:")
    await repo.save_auto("f1", ME, nodes=["sc6"], goals=[], version="v1")

    await repo.set_tag("f1", "goal", "ff-mgmt5", "mahamudul")

    assert ("goal", "ff-mgmt5", 1, "user") in _view(await _tags(repo))
    stats = await repo.feedback_stats(EPOCH)
    assert (stats.edits, stats.corrections) == (1, 0)  # an add is not a correction


async def test_edits_on_an_unprocessed_fact_fail() -> None:
    repo = SqliteFactTags(":memory:")
    with pytest.raises(FactNotTaggedError):
        await repo.set_tag("ghost", "node", "sc4", "u")
    with pytest.raises(FactNotTaggedError):
        await repo.remove("ghost", "node", "u")
    with pytest.raises(FactNotTaggedError):
        await repo.accept("ghost", "node", "u")


async def test_accept_and_remove_without_a_tag_do_nothing() -> None:
    repo = SqliteFactTags(":memory:")
    await repo.save_auto("f1", ME, nodes=[], goals=[], version="v1")

    await repo.accept("f1", "node", "u")
    await repo.remove("f1", "node", "u")

    assert (await repo.feedback_stats(EPOCH)).edits == 0


async def test_user_tags_carry_over_to_the_new_version_of_a_fact() -> None:
    repo = SqliteFactTags(":memory:")
    await _tagged(repo, "old")
    await repo.set_tag("old", "node", "fi4", "mahamudul")

    copied = await repo.copy_user_tags("old", "new", ME)
    await repo.save_auto("new", ME, nodes=["sc6"], goals=["ff-mgmt5"], version="v1")

    assert copied == 1
    assert _view(await _tags(repo, "new")) == [
        ("goal", "ff-mgmt5", 1, "auto"),
        ("node", "fi4", 1, "user"),
    ]
    assert await repo.copy_user_tags("nothing", "new2", ME) == 0


async def test_counts_and_gaps_only_cover_the_given_scopes() -> None:
    repo = SqliteFactTags(":memory:")
    await _tagged(repo, "f1", ME)
    await _tagged(repo, "f2", ME)
    await _tagged(repo, "f3", OTHER)
    await repo.save_auto("f4", ME, nodes=["sc4"], goals=[], version="v1")

    counts = {(c.kind, c.tag): c.facts for c in await repo.counts([ME])}
    assert counts == {("goal", "ff-mgmt5"): 2, ("node", "sc6"): 2, ("node", "sc4"): 1}
    assert await repo.counts([]) == []
    assert await repo.without("goal", [ME], limit=10, offset=0) == ["f4"]
    assert await repo.without("goal", [OTHER], limit=10, offset=0) == []
    assert await repo.without("goal", [], limit=10, offset=0) == []


async def test_feedback_stats_only_count_edits_in_the_window() -> None:
    repo = SqliteFactTags(":memory:")
    await _tagged(repo)
    await repo.set_tag("f1", "node", "fi4", "u")

    stats = await repo.feedback_stats("2999-01-01")
    assert (stats.edits, stats.corrections, stats.confusions) == (0, 0, [])
