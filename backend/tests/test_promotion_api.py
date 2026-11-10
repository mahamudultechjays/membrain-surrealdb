import asyncio
from collections.abc import Iterator
from datetime import date

import pytest
from fastapi.testclient import TestClient

from app.adapters.sqlite import SqlitePromotion
from app.composition import get_promotion_repository, get_promotion_service, get_team_rules
from app.domain.ports.promotion import FactGroup, ReviewItem, Statement
from app.domain.promotion import Weights
from app.main import app
from app.services.access import AccessService
from app.services.promotion.decisions import closing_text
from app.services.promotion.service import PromotionService
from tests.conftest import sign_in

ADMIN, PRIYA, BOB = "admin@x.com", "priya.shah@x.com", "bob@x.com"


class Writer:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def write(self, **kwargs: object) -> str:
        self.calls.append(kwargs)
        return f"a{len(self.calls)}"


class Nothing:
    async def match(self, *a: object, **k: object) -> list[object]:
        return []

    async def all_grants(self) -> list[object]:
        return []


@pytest.fixture
def repo() -> SqlitePromotion:
    return SqlitePromotion(":memory:")


@pytest.fixture
def writer() -> Writer:
    return Writer()


@pytest.fixture
def client(access: AccessService, repo: SqlitePromotion, writer: Writer) -> Iterator[TestClient]:
    service = PromotionService(
        repo,
        Nothing(),  # type: ignore[arg-type]
        Nothing(),  # type: ignore[arg-type]
        Nothing(),  # type: ignore[arg-type]
        weights=Weights(1, 0.5),
        personal_rule_at=1.75,
        candidate_at=3,
        flag_at=2,
        batch_size=5,
        generic_subjects=frozenset(),
    )
    app.dependency_overrides[get_promotion_repository] = lambda: repo
    app.dependency_overrides[get_promotion_service] = lambda: service
    app.dependency_overrides[get_team_rules] = lambda: writer
    with TestClient(app) as test_client:
        sign_in(test_client, PRIYA, "Priya Shah")
        sign_in(test_client, BOB, "Bob")
        sign_in(test_client, ADMIN, "Ada Admin")
        yield test_client
    app.dependency_overrides.clear()


async def _seed(repo: SqlitePromotion) -> tuple[int, int]:
    group = FactGroup(
        "Cobalt Ridge return window",
        "cobalt ridge",
        "organization",
        "Cobalt Ridge",
        "return_window",
    )
    gid = await repo.add_group(group)
    rows = [
        Statement(u, "s", f"r{u}", "chat", "t", "cobalt_ridge", "rw", "30 days", u)
        for u in ("a", "b", "c")
    ]
    await repo.add_statements(rows)
    grouped = [(s.id, gid, "30 days", "for") for s in await repo.unprocessed(10) if s.id]
    await repo.set_grouping(grouped, "now")  # type: ignore[arg-type]
    iid = await repo.add_review_item(ReviewItem("candidate", gid, "30 days", 3, "open"))
    return gid, iid


def seed(repo: SqlitePromotion) -> tuple[int, int]:
    return asyncio.run(_seed(repo))


def test_get_promotion_lists_items_with_scores(client: TestClient, repo: SqlitePromotion) -> None:
    seed(repo)
    body = client.get("/api/v1/promotion").json()
    (item,) = body["items"]
    assert item["label"] == "Cobalt Ridge return window"
    assert (item["value"], item["team_score"], item["holders"]) == ("30 days", 3, ["a", "b", "c"])
    assert body["thresholds"]["candidate_at"] == 3
    assert item["values"] == [{"value": "30 days", "team_score": 3}]
    assert item["people"] == 3
    assert [r["user"] for r in item["for_rows"]] == ["a", "b", "c"]
    assert item["for_rows"][0]["said"] == [{"text": "t", "source": "chat", "said_at": "a"}]
    assert item["against_rows"] == []
    assert body["groups"] == [
        {
            "id": 1,
            "label": "Cobalt Ridge return window",
            "values": [{"value": "30 days", "team_score": 3}],
            "people": 3,
        }
    ]


def test_approve_writes_labelled_rule_and_activates(
    client: TestClient, repo: SqlitePromotion, writer: Writer
) -> None:
    _, iid = seed(repo)
    body = client.post(f"/api/v1/promotion/items/{iid}/approve").json()
    assert writer.calls == [
        {
            "entity_type": "organization",
            "entity": "Cobalt Ridge",
            "key": "return_window",
            "value": "30 days",
            "labels": ["kind=rule", f"approved_by={ADMIN}"],
        }
    ]
    (item,) = body["items"]
    assert (item["status"], item["decided_by"]) == ("active", ADMIN)


def test_approve_with_edit_uses_edited_entity_key_value(
    client: TestClient, repo: SqlitePromotion, writer: Writer
) -> None:
    _, iid = seed(repo)
    edit = {
        "label": "CR returns",
        "entity_type": "company",
        "entity": "Cobalt Ridge Inc",
        "key": "returns_window",
        "value": "30 calendar days",
    }
    body = client.post(f"/api/v1/promotion/items/{iid}/approve", json=edit).json()
    call = writer.calls[0]
    assert (call["entity"], call["key"], call["value"]) == (
        "Cobalt Ridge Inc",
        "returns_window",
        "30 calendar days",
    )
    assert body["items"][0]["label"] == "CR returns"


def test_approve_wrong_status_is_409_and_writes_nothing(
    client: TestClient, repo: SqlitePromotion, writer: Writer
) -> None:
    _, iid = seed(repo)
    assert client.post(f"/api/v1/promotion/items/{iid}/reject").status_code == 200
    assert client.post(f"/api/v1/promotion/items/{iid}/approve").status_code == 409
    assert client.post("/api/v1/promotion/items/999/approve").status_code == 409
    assert writer.calls == []


def test_close_flag_closes_rule_with_closing_value(
    client: TestClient, repo: SqlitePromotion, writer: Writer
) -> None:
    gid, iid = seed(repo)
    client.post(f"/api/v1/promotion/items/{iid}/approve")
    fid = asyncio.run(
        repo.add_review_item(ReviewItem("flag", gid, "30 days", 2, "open", rule_id=iid))
    )
    assert client.post(f"/api/v1/promotion/items/{fid}/close").status_code == 200
    closing = writer.calls[1]
    assert str(closing["value"]).startswith(f"no longer a team rule (closed by {ADMIN} on ")
    assert closing["labels"] == ["kind=closed", f"closed_by={ADMIN}"]
    assert {i.status for i in asyncio.run(repo.review_items())} == {"closed"}
    assert asyncio.run(repo.closed_rule_refs()) == {"a1", "a2"}


def test_team_admin_can_decide_and_other_users_get_403(
    client: TestClient, repo: SqlitePromotion
) -> None:
    _, iid = seed(repo)
    client.put(f"/api/v1/admin/team-admins/{PRIYA}")
    sign_in(client, BOB, "Bob")
    assert client.get("/api/v1/promotion").status_code == 403
    sign_in(client, PRIYA, "Priya Shah")
    assert client.post(f"/api/v1/promotion/items/{iid}/reject").status_code == 200


def test_run_now_starts_a_run(client: TestClient) -> None:
    assert client.post("/api/v1/promotion/run").status_code in (202, 409)


def test_closing_text() -> None:
    assert closing_text("ana@spreetail.com", date(2026, 11, 12)) == (
        "no longer a team rule (closed by ana@spreetail.com on 12 Nov)"
    )
