import asyncio
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.adapters.sqlite import SqliteFactTags
from app.main import app
from app.services.access import AccessService
from tests.conftest import sign_in

PRIYA = "org/spreetail/user/priya_shah"
ARUN = "org/spreetail/user/arun_das"


@pytest.fixture
def client(access: AccessService, tags: SqliteFactTags) -> Iterator[TestClient]:
    nodes = ["mo1", "fi4", "sc9"]
    asyncio.run(tags.save_auto("f1", PRIYA, nodes=nodes, goals=["ps-mgmt3"], version="v1"))
    asyncio.run(tags.save_auto("f2", ARUN, nodes=["sc6"], goals=["ff-mgmt5"], version="v1"))
    asyncio.run(tags.save_auto("f3", PRIYA, nodes=["sc6"], goals=[], version="v1"))
    with TestClient(app) as test_client:
        sign_in(test_client, "arun.das@x.com", "Arun Das")
        sign_in(test_client, "priya.shah@x.com", "Priya Shah")
        yield test_client
    app.dependency_overrides.clear()


def _edit(client: TestClient, fact: str, **body: str) -> dict:  # type: ignore[type-arg]
    response = client.put(f"/api/v1/facts/{fact}/tags", json=body)
    assert response.status_code == 200, response.text
    return response.json()  # type: ignore[no-any-return]


def test_read_a_fact_s_tags_with_alternatives(client: TestClient) -> None:
    body = client.get("/api/v1/facts/attribute:f1/tags").json()

    assert body["fact_id"] == "f1"
    assert body["scope"] == PRIYA
    assert [(n["id"], n["rank"]) for n in body["nodes"]] == [("mo1", 1), ("fi4", 2), ("sc9", 3)]
    assert body["nodes"][1]["domain_id"] == "finance"
    assert body["goals"][0]["id"] == "ps-mgmt3"
    assert body["goals"][0]["section"]


def test_change_remove_and_accept(client: TestClient, tags: SqliteFactTags) -> None:
    changed = _edit(client, "f1", kind="node", action="change", tag="fi4")
    removed = _edit(client, "f1", kind="goal", action="remove")
    accepted = _edit(client, "f3", kind="node", action="accept")
    added = _edit(client, "f3", kind="goal", action="change", tag="ff-mgmt5")

    assert [(n["id"], n["source"]) for n in changed["nodes"]] == [("fi4", "user")]
    assert removed["goals"] == []
    assert accepted["nodes"][0]["source"] == "user"
    assert added["goals"][0]["id"] == "ff-mgmt5"
    stats = asyncio.run(tags.feedback_stats("2000-01-01"))
    assert (stats.edits, stats.corrections) == (4, 2)


def test_a_change_needs_a_known_tag_of_that_kind(client: TestClient) -> None:
    for body in (
        {"kind": "node", "action": "change", "tag": "ff-mgmt5"},
        {"kind": "goal", "action": "change", "tag": "sc6"},
        {"kind": "node", "action": "change"},
    ):
        assert client.put("/api/v1/facts/f1/tags", json=body).status_code == 422


def test_only_readers_of_the_fact_s_scope_may_see_or_edit(client: TestClient) -> None:
    edit = {"kind": "node", "action": "remove"}

    assert client.get("/api/v1/facts/f2/tags").status_code == 403
    assert client.put("/api/v1/facts/f2/tags", json=edit).status_code == 403
    assert client.get("/api/v1/facts/ghost/tags").status_code == 404
    assert client.put("/api/v1/facts/ghost/tags", json=edit).status_code == 404

    sign_in(client, "admin@x.com", "Ada Admin")
    assert client.get("/api/v1/facts/f2/tags").status_code == 200


def test_coverage_counts_only_readable_scopes(client: TestClient) -> None:
    body = client.get("/api/v1/vct/coverage").json()

    assert body["scopes"] == ["org/spreetail", PRIYA]
    assert body["tagged_facts"] == 2
    assert body["without_goal"] == 1
    assert {c["id"]: c["facts"] for c in body["nodes"]} == {"mo1": 1, "sc6": 1}
    assert {c["id"]: c["facts"] for c in body["goals"]} == {"ps-mgmt3": 1}
    cells = body["cells"]
    assert sum(c["nodes"] for c in cells) == 41
    assert sum(c["facts"] for c in cells) == 2
    assert any(c["nodes"] and not c["facts"] for c in cells)  # gaps show


def test_vct_routes_need_sign_in(access: AccessService) -> None:
    with TestClient(app) as anonymous:
        assert anonymous.get("/api/v1/facts/f1/tags").status_code == 401
        assert anonymous.get("/api/v1/vct/coverage").status_code == 401
    app.dependency_overrides.clear()


def test_the_map_lists_goals_by_section(client: TestClient) -> None:
    body = client.get("/api/v1/vct/map").json()

    assert len(body["sections"]) == 7
    assert sum(len(s["goals"]) for s in body["sections"]) == 42
    assert body["sections"][0]["goals"][0].keys() == {"id", "name", "description", "weight"}
    assert all(n["section_id"] for d in body["domains"] for n in d["nodes"])
