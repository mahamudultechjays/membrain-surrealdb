"""Reviewing new VCT tags: confirm, not business, keep, tag it, and in bulk."""

import asyncio
from collections.abc import Coroutine, Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.adapters.sqlite import SqliteFactTags
from app.main import app
from app.services.access import AccessService
from tests.conftest import sign_in

PRIYA = "org/spreetail/user/priya_shah"
ARUN = "org/spreetail/user/arun_das"


def _run(coro: Coroutine[Any, Any, Any]) -> Any:
    return asyncio.run(coro)


async def test_store_tracks_review_and_keeps_guesses_for_not_business() -> None:
    tags = SqliteFactTags(":memory:")
    await tags.save_auto("f1", PRIYA, nodes=["sc6", "sc7"], goals=["ff-mgmt5"], version="v1")
    await tags.save_auto(
        "f2", PRIYA, nodes=["cs2", "mo1"], goals=["ps-mgmt2"], version="v1", business=False
    )

    state = await tags.review_state(["f1", "f2", "nope"])
    assert set(state) == {"f1", "f2"}
    assert state["f1"].reviewed_at is None
    assert state["f1"].tagged_at
    assert "f2" not in await tags.tags_for(["f2"])
    assert await tags.guesses("f2") == {"goal": ["ps-mgmt2"], "node": ["cs2", "mo1"]}
    assert await tags.guesses("f1") == {}
    assert await tags.review_state([]) == {}

    await tags.confirm("f1", "priya")
    after = (await tags.review_state(["f1"]))["f1"]
    assert after.reviewed_by == "priya"
    assert {t.source for t in (await tags.tags_for(["f1"]))["f1"] if t.rank == 1} == {"user"}


async def test_marking_not_business_moves_tags_to_guesses_and_keep_only_reviews() -> None:
    tags = SqliteFactTags(":memory:")
    await tags.save_auto("f1", PRIYA, nodes=["sc6", "sc7"], goals=["ff-mgmt5"], version="v1")

    await tags.mark_not_business("f1", "priya")
    await tags.keep("f1", "arun")

    assert await tags.not_business(["f1"]) == {"f1"}
    assert await tags.tags_for(["f1"]) == {}
    assert await tags.guesses("f1") == {"goal": ["ff-mgmt5"], "node": ["sc6", "sc7"]}
    assert (await tags.review_state(["f1"]))["f1"].reviewed_by == "arun"
    stats = await tags.feedback_stats("2000-01-01")
    assert stats.corrections == 2  # both removals count against the tagger

    # Setting a tag makes it business again and clears that kind's guesses.
    await tags.set_tag("f1", "node", "sc6", "priya")
    assert await tags.not_business(["f1"]) == set()
    assert await tags.guesses("f1") == {"goal": ["ff-mgmt5"]}


@pytest.fixture
def client(access: AccessService, tags: SqliteFactTags) -> Iterator[TestClient]:
    _run(tags.save_auto("f1", PRIYA, nodes=["sc6", "sc7"], goals=["ff-mgmt5"], version="v1"))
    _run(tags.save_auto("f2", PRIYA, nodes=["sc4"], goals=["ff-mgmt1"], version="v1"))
    _run(
        tags.save_auto(
            "f3", PRIYA, nodes=["cs2", "mo1"], goals=["ps-mgmt2"], version="v1", business=False
        )
    )
    _run(tags.save_auto("f9", ARUN, nodes=["sc6"], goals=["ff-mgmt5"], version="v1"))
    with TestClient(app) as test_client:
        sign_in(test_client, "arun.das@x.com", "Arun Das")
        sign_in(test_client, "priya.shah@x.com", "Priya Shah")
        yield test_client
    app.dependency_overrides.clear()


def _act(client: TestClient, fact: str, **body: str) -> dict[str, Any]:
    response = client.put(f"/api/v1/facts/{fact}/tags", json=body)
    assert response.status_code == 200, response.text
    return response.json()  # type: ignore[no-any-return]


def test_detail_shows_review_state_and_guesses(client: TestClient) -> None:
    plain = client.get("/api/v1/facts/f1/tags").json()
    guessed = client.get("/api/v1/facts/f3/tags").json()

    assert plain["tagged_at"]
    assert plain["reviewed_at"] is None
    assert plain["guess_nodes"] == []
    assert guessed["business"] is False
    assert [g["id"] for g in guessed["guess_nodes"]] == ["cs2", "mo1"]
    assert [g["id"] for g in guessed["guess_goals"]] == ["ps-mgmt2"]


def test_review_actions_on_one_fact(client: TestClient) -> None:
    confirmed = _act(client, "f1", action="confirm")
    tagged = _act(client, "f3", action="tag_guesses")
    dropped = _act(client, "f2", action="not_business")

    assert confirmed["reviewed_by"] == "priya.shah@x.com"
    assert (confirmed["nodes"][0]["id"], confirmed["nodes"][0]["source"]) == ("sc6", "user")
    assert tagged["business"] is True
    assert [n["id"] for n in tagged["nodes"]] == ["cs2"]
    assert [g["id"] for g in tagged["goals"]] == ["ps-mgmt2"]
    assert dropped["business"] is False
    assert dropped["nodes"] == []
    assert [g["id"] for g in dropped["guess_nodes"]] == ["sc4"]
    assert _act(client, "f2", action="keep")["reviewed_at"]


def test_tag_guesses_needs_guesses_and_kind_actions_need_a_kind(client: TestClient) -> None:
    assert client.put("/api/v1/facts/f1/tags", json={"action": "tag_guesses"}).status_code == 409
    assert client.put("/api/v1/facts/f1/tags", json={"action": "remove"}).status_code == 422


def test_bulk_confirm_skips_what_the_caller_cannot_read(client: TestClient) -> None:
    response = client.post(
        "/api/v1/facts/review",
        json={"fact_ids": ["f1", "attribute:f2", "f9", "ghost", "f1"], "action": "confirm"},
    )

    assert response.status_code == 200
    assert response.json() == {"done": ["f1", "f2"], "skipped": ["f9", "ghost"]}
    assert client.get("/api/v1/facts/f2/tags").json()["reviewed_at"]
    keep = client.post("/api/v1/facts/review", json={"fact_ids": ["f3"], "action": "keep"})
    assert keep.json()["done"] == ["f3"]
