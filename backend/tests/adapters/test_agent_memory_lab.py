from typing import Any

import pytest
from surrealdb_memory import MemoryAPIError
from surrealdb_memory._models.memory import RememberResponse

from app.adapters.agent_memory import AgentMemoryLab, NotConfiguredLab
from app.domain.errors import MemoryNotConfiguredError, MemoryUnavailableError
from app.domain.ports.memory_lab import LabCounts

BASE = "/api/v1/ctx"
LAB = "org/spreetail/lab/run-1"
OTHER = "org/spreetail/user/arun_das"


def _attr(id: str, kind: str, scope: str = LAB) -> dict[str, Any]:
    return {"id": id, "scope": [[f"{scope}/"]], "source": {"kind": kind}}


# Shapes as Agent Memory returned them live on 2026-11-04.
LISTINGS: dict[str, list[dict[str, Any]]] = {
    "entities": [
        {"id": "['organisation', 'harbor_freight_lines']", "name": "Harbor Freight Lines"},
        {"id": "['location', 'denver']", "name": "Denver"},
    ],
    "attributes": [_attr("a1", "turn"), _attr("a2", "turn"), _attr("a9", "turn", OTHER)],
    "relations": [_attr("r1", "turn"), _attr("r2", "elaboration")],
}
CONSOLIDATE = {
    "traceId": "tr-c",
    "created": 2,
    "updated": 0,
    "superseded": 0,
    "dryRun": True,
    "outcomes": [
        {
            "kind": "create",
            "entityName": "Harbor Freight Lines",
            "key": "lead_time_to_denver",
            "value": "6 days",
            "proofCount": 1,
            "rationale": "Direct fact.",
        }
    ],
}
SERVES = {"subject": "Harbor Freight Lines", "label": "serves", "object": "Denver"}
REFLECT = {
    "reflection": "One carrier serves Denver.",
    "evidence": ["Harbor Freight Lines is our carrier for the Denver warehouse."],
    "persistedAttributes": [{"summary": "Denver has a single carrier"}],
    "traceId": "tr-r",
}


class FakeTransport:
    def __init__(self, log: list[tuple[str, str, Any]], name: str) -> None:
        self.log = log
        self.name = name
        self.error: Exception | None = None

    async def request(
        self, method: str, path: str, *, json: Any = None, params: Any = None, **_: Any
    ) -> Any:
        call = f"{method} {path.removeprefix(BASE)}"
        self.log.append((self.name, call, json if json is not None else params))
        if self.error:
            raise self.error
        if call == "POST /keys":
            return {"id": "k1", "key": f"secret-{len(self.log)}"}
        if method == "GET":
            kind = call.removeprefix("GET /")
            return {kind: LISTINGS[kind], "page": {"hasMore": False}}
        if call == "POST /consolidate":
            return CONSOLIDATE
        if call == "POST /reflect":
            return REFLECT
        if call == "POST /elaborate":
            emitted = 2 if json["entityRef"] == "organisation/harbor_freight_lines" else 0
            return {
                "relationsEmitted": emitted,
                "outcomes": [
                    {
                        "entityName": json["entityRef"],
                        "relationsEmitted": emitted,
                        "traceId": f"tr-{json['entityRef']}",
                        "proposedRelations": [
                            {
                                "subject": "Harbor Freight Lines",
                                "label": "serves",
                                "object": "Denver",
                            }
                        ]
                        if emitted
                        else [],
                    }
                ],
            }
        return {}


class FakeClient:
    def __init__(self, log: list[tuple[str, str, Any]], name: str) -> None:
        self._base = BASE
        self._transport = FakeTransport(log, name)
        self.closed = False
        self.remembered: list[tuple[str, dict[str, Any]]] = []

    async def remember(self, text: str, **kwargs: Any) -> RememberResponse:
        self.remembered.append((text, kwargs))
        return RememberResponse.from_dict(
            {
                "mode": "full",
                "sessionId": "s1",
                "extraction": {
                    "entities": [{"id": "e1", "name": "Denver"}],
                    "attributes": [{"summary": "Denver returns window is 45 days"}],
                    "relations": [],
                },
            }
        )

    async def close(self) -> None:
        self.closed = True


class Setup:
    def __init__(self) -> None:
        self.log: list[tuple[str, str, Any]] = []
        self.admin = FakeClient(self.log, "admin")
        self.users: list[FakeClient] = []
        self.lab = AgentMemoryLab(self.admin, self.connect)  # type: ignore[arg-type]

    def connect(self, key: str) -> FakeClient:
        self.users.append(FakeClient(self.log, key))
        return self.users[-1]

    def calls(self, who: str, prefix: str) -> list[Any]:
        return [body for name, call, body in self.log if name == who and call.startswith(prefix)]

    @property
    def user(self) -> FakeClient:
        return self.users[-1]


@pytest.fixture
def setup() -> Setup:
    return Setup()


async def test_runs_with_a_key_that_reads_and_writes_only_the_lab_scope(setup: Setup) -> None:
    await setup.lab.counts(LAB)

    [mint] = setup.calls("admin", "POST /keys")
    assert mint["grants"] == {"memory:read": [LAB], "memory:write": [LAB]}
    assert setup.calls("admin", "GET") == []


async def test_counts_only_records_in_the_lab_scope_by_source(setup: Setup) -> None:
    counts = await setup.lab.counts(LAB)

    assert counts == LabCounts(
        entities=2, attributes=2, relations=2, by_source={"turn": 3, "elaboration": 1}
    )


async def test_key_is_minted_once_per_scope(setup: Setup) -> None:
    await setup.lab.counts(LAB)
    await setup.lab.consolidate(LAB, dry_run=True)

    assert len(setup.calls("admin", "POST /keys")) == 1


async def test_consolidate_passes_dry_run_and_lists_outcomes(setup: Setup) -> None:
    outcome = await setup.lab.consolidate(LAB, dry_run=True)

    assert setup.calls(setup.user._transport.name, "POST /consolidate") == [{"dryRun": True}]
    assert outcome.summary == {"created": 2, "updated": 0, "superseded": 0}
    assert outcome.items == [
        "create · Harbor Freight Lines · lead_time_to_denver = 6 days (proof 1) · Direct fact."
    ]
    assert outcome.trace_ids == ["tr-c"]


async def test_elaborate_goes_entity_by_entity_in_the_scope(setup: Setup) -> None:
    outcome = await setup.lab.elaborate(LAB, dry_run=False)

    bodies = setup.calls(setup.user._transport.name, "POST /elaborate")
    assert bodies == [
        {"entityRef": "organisation/harbor_freight_lines", "dryRun": False},
        {"entityRef": "location/denver", "dryRun": False},
    ]
    assert outcome.summary == {"entities": 2, "relations": 2}
    assert outcome.items == ["Harbor Freight Lines serves Denver"]


async def test_reflect_returns_the_synthesis_evidence_and_saved_facts(setup: Setup) -> None:
    outcome = await setup.lab.reflect(LAB, "Carriers?", persist=True)

    assert setup.calls(setup.user._transport.name, "POST /reflect") == [
        {"query": "Carriers?", "persist": True}
    ]
    assert outcome.text == "One carrier serves Denver."
    assert outcome.summary == {"evidence": 1, "saved": 1}
    assert outcome.items == [
        "evidence: Harbor Freight Lines is our carrier for the Denver warehouse.",
        "saved: Denver has a single carrier",
    ]


async def test_whole_context_consolidation_uses_the_admin_key(setup: Setup) -> None:
    outcome = await setup.lab.consolidate(None, dry_run=True)

    assert setup.calls("admin", "POST /consolidate") == [{"dryRun": True}]
    assert setup.calls("admin", "POST /keys") == []
    assert outcome.summary["created"] == 2


async def test_whole_context_can_use_its_own_slower_admin_client() -> None:
    log: list[tuple[str, str, Any]] = []
    admin, whole = FakeClient(log, "admin"), FakeClient(log, "whole")
    lab = AgentMemoryLab(admin, lambda key: FakeClient(log, key), whole=whole)  # type: ignore[arg-type]

    await lab.consolidate(None, dry_run=True)
    await lab.close()

    assert [(n, c) for n, c, _ in log] == [("whole", "POST /consolidate")]
    assert whole.closed
    assert not admin.closed


async def test_whole_context_counts_everything_the_admin_key_sees(setup: Setup) -> None:
    counts = await setup.lab.counts(None)

    assert (counts.attributes, counts.relations) == (3, 2)
    assert setup.calls("admin", "POST /keys") == []


async def test_failure_is_unavailable(setup: Setup) -> None:
    await setup.lab.counts(LAB)
    setup.user._transport.error = MemoryAPIError(500, "boom")

    with pytest.raises(MemoryUnavailableError):
        await setup.lab.consolidate(LAB, dry_run=False)


async def test_close_deletes_the_minted_keys(setup: Setup) -> None:
    await setup.lab.counts(LAB)

    await setup.lab.close()

    assert len([c for _, c, _ in setup.log if c.startswith("DELETE /keys/")]) == 1
    assert setup.user.closed


async def test_not_configured() -> None:
    with pytest.raises(MemoryNotConfiguredError):
        await NotConfiguredLab().counts(LAB)
