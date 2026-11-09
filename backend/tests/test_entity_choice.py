import pytest

from app.domain.ports.memory_capture import (
    CaptureResult,
    ExtractedAttribute,
    ExtractedEntity,
    FactTriple,
)
from app.services import capture_flow

ARUN = "org/spreetail/user/arun"


class TwoEntityCapture:
    """A preview like Agent Memory's: two entities, attributes with no entity link."""

    def __init__(self) -> None:
        self.stored: list[FactTriple] = []

    async def preview(self, text: str, scope: str | None = None) -> CaptureResult:
        return CaptureResult(
            mode="preview",
            session_id="s1",
            entities=[
                ExtractedEntity("Acme Logistics", "organisation", "context", is_new=True),
                ExtractedEntity("Dock 3", "location", "context", is_new=True),
            ],
            attributes=[
                ExtractedAttribute("lead_time", "18 days", "context"),
                ExtractedAttribute("status", "closed", "context"),
            ],
        )

    async def store(self, text: str, scope: str | None = None) -> CaptureResult:
        raise AssertionError("full mode is not used here")

    async def store_facts(self, facts: list[FactTriple], scope: str) -> CaptureResult:
        self.stored = facts
        return CaptureResult(mode="stored", session_id="s2")

    async def store_passage(self, text: str, scope: str) -> str | None:
        return "t-passage"


async def _preview(capture: TwoEntityCapture) -> capture_flow.Preview:
    return await capture_flow.preview(
        capture, owner="arun.das@example.com", scope=ARUN, text="...", source="text"
    )


async def test_unlinked_facts_offer_the_preview_entities() -> None:
    found = await _preview(TwoEntityCapture())

    unlinked = [f for f in found.facts if f.unlinked]
    assert [f.fact for f in unlinked] == ["? · lead_time = 18 days", "? · status = closed"]
    assert all(f.triple is None for f in unlinked)
    assert [e.name for e in found.entities] == ["Acme Logistics", "Dock 3"]


async def test_a_picked_entity_stores_the_fact_as_a_triple() -> None:
    capture = TwoEntityCapture()
    found = await _preview(capture)
    lead, status = (f.id for f in found.facts if f.unlinked)

    outcome = await capture_flow.store(
        capture,
        found,
        kept=[lead, status],
        mode="triples",
        memory_category=None,
        entity_choices={lead: "Acme Logistics", status: "Dock 3"},
    )

    assert outcome.written == 2
    assert [(t.entity_name, t.entity_type, t.key, t.value) for t in capture.stored] == [
        ("Acme Logistics", "organisation", "lead_time", "18 days"),
        ("Dock 3", "location", "status", "closed"),
    ]


async def test_an_unlinked_fact_without_a_choice_is_still_skipped() -> None:
    capture = TwoEntityCapture()
    found = await _preview(capture)
    lead, status = (f.id for f in found.facts if f.unlinked)

    await capture_flow.store(
        capture,
        found,
        kept=[lead, status],
        mode="triples",
        memory_category=None,
        entity_choices={lead: "Acme Logistics"},
    )

    assert [t.key for t in capture.stored] == ["lead_time"]


async def test_entity_choices_are_checked() -> None:
    capture = TwoEntityCapture()
    found = await _preview(capture)
    lead = next(f.id for f in found.facts if f.unlinked)
    linked = next(f.id for f in found.facts if f.triple)

    with pytest.raises(capture_flow.CaptureFlowError, match="not an entity found"):
        await capture_flow.store(
            capture,
            found,
            kept=[lead],
            mode="triples",
            memory_category=None,
            entity_choices={lead: "Somebody Else"},
        )
    with pytest.raises(capture_flow.CaptureFlowError, match="does not need"):
        await capture_flow.store(
            capture,
            found,
            kept=[linked],
            mode="triples",
            memory_category=None,
            entity_choices={linked: "Dock 3"},
        )
