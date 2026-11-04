from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.composition import get_memory_lab
from app.domain.errors import MemoryNotConfiguredError, MemoryUnavailableError
from app.domain.ports.memory_lab import LabCounts, LabOutcome
from app.main import app
from app.services.access import AccessService
from tests.conftest import sign_in

SCOPE = "org/spreetail/user/vidyul_narayanan"
RUNS = "/api/v1/admin/lab/runs"


class FakeLab:
    """Counts grow by one attribute per saving run; records every call."""

    def __init__(self) -> None:
        self.calls: list[tuple[Any, ...]] = []
        self.attributes = 9
        self.error: Exception | None = None

    async def counts(self, scope: str | None) -> LabCounts:
        self.calls.append(("counts", scope))
        if self.error:
            raise self.error
        return LabCounts(
            entities=3, attributes=self.attributes, relations=2, by_source={"turn": self.attributes}
        )

    def _ran(self, *call: Any, saves: bool) -> LabOutcome:
        self.calls.append(call)
        if saves:
            self.attributes += 1
        return LabOutcome(summary={"created": 1}, items=["create · x"], trace_ids=["tr"])

    async def consolidate(self, scope: str | None, *, dry_run: bool) -> LabOutcome:
        return self._ran("consolidate", scope, dry_run, saves=not dry_run)

    async def elaborate(self, scope: str, *, dry_run: bool) -> LabOutcome:
        return self._ran("elaborate", scope, dry_run, saves=not dry_run)

    async def reflect(self, scope: str, query: str, *, persist: bool) -> LabOutcome:
        self.calls.append(("reflect", scope, query, persist))
        return LabOutcome(summary={"evidence": 1, "saved": 0}, text="A synthesis.")


@pytest.fixture
def lab() -> FakeLab:
    return FakeLab()


@pytest.fixture
def client(access: AccessService, lab: FakeLab) -> Iterator[TestClient]:
    app.dependency_overrides[get_memory_lab] = lambda: lab
    with TestClient(app) as test_client:
        sign_in(test_client, "admin@x.com", "Ada Admin")
        yield test_client
    app.dependency_overrides.clear()


def _run(client: TestClient, **body: Any) -> Any:
    response = client.post(RUNS, json={"scope": SCOPE, **body})
    assert response.status_code == 200, response.text
    return response.json()


def test_a_run_counts_before_and_after(client: TestClient, lab: FakeLab) -> None:
    body = _run(client, action="consolidate")

    assert ("consolidate", SCOPE, False) in lab.calls
    assert body["before"]["attributes"] == 9
    assert body["after"]["attributes"] == 10
    assert body["outcome"]["summary"] == {"created": 1}
    assert body["outcome"]["items"] == ["create · x"]
    assert (body["action"], body["scope"]) == ("consolidate", SCOPE)


@pytest.mark.parametrize("scope", ["org/spreetail", "org/spreetail/team/ops", SCOPE])
def test_any_scope_under_the_org_can_be_used(client: TestClient, lab: FakeLab, scope: str) -> None:
    _run(client, action="elaborate", dry_run=True, scope=scope)

    assert ("elaborate", scope, True) in lab.calls


def test_reflect_passes_the_question_and_save_choice(client: TestClient, lab: FakeLab) -> None:
    body = _run(client, action="reflect", query="Carriers?", persist=True)

    assert ("reflect", SCOPE, "Carriers?", True) in lab.calls
    assert body["outcome"]["text"] == "A synthesis."


def test_whole_context_is_a_consolidation_preview(client: TestClient, lab: FakeLab) -> None:
    body = _run(client, action="consolidate", dry_run=True, scope=None)

    assert ("consolidate", None, True) in lab.calls
    assert ("counts", None) in lab.calls
    assert body["scope"] is None


@pytest.mark.parametrize(
    "body",
    [
        {"action": "consolidate", "dry_run": False, "scope": None},
        {"action": "elaborate", "dry_run": True, "scope": None},
        {"action": "reflect", "query": "x", "scope": None},
    ],
)
def test_whole_context_only_previews_consolidation(
    client: TestClient, lab: FakeLab, body: dict[str, Any]
) -> None:
    assert client.post(RUNS, json=body).status_code == 422
    assert lab.calls == []


@pytest.mark.parametrize(
    "body",
    [
        {"action": "reflect"},
        {"action": "reflect", "query": "  "},
        {"action": "decay"},
        {"action": "count"},
    ],
)
def test_missing_question_or_unknown_action_is_422(
    client: TestClient, lab: FakeLab, body: dict[str, Any]
) -> None:
    assert client.post(RUNS, json={"scope": SCOPE, **body}).status_code == 422
    assert lab.calls == []


@pytest.mark.parametrize("scope", ["", "org", "other/place", "org/spreetailx"])
def test_scopes_outside_the_org_are_refused(client: TestClient, lab: FakeLab, scope: str) -> None:
    response = client.post(RUNS, json={"scope": scope, "action": "consolidate"})

    assert response.status_code == 422
    assert lab.calls == []


@pytest.mark.parametrize("error", [MemoryNotConfiguredError(), MemoryUnavailableError("down")])
def test_memory_failure_is_503(client: TestClient, lab: FakeLab, error: Exception) -> None:
    lab.error = error

    assert client.post(RUNS, json={"scope": SCOPE, "action": "consolidate"}).status_code == 503


def test_non_admin_is_403(client: TestClient) -> None:
    sign_in(client, "priya.shah@x.com", "Priya Shah")

    assert client.post(RUNS, json={"scope": SCOPE, "action": "consolidate"}).status_code == 403


def test_signed_out_is_401(client: TestClient) -> None:
    client.post("/api/v1/auth/logout")

    assert client.post(RUNS, json={"scope": SCOPE, "action": "consolidate"}).status_code == 401
