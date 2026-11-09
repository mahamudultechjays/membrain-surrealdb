"""Memory chunks share their facts' VCT tags: capture links facts to the text's
turn, the tagger records turns, and Ask's value filter keeps a chunk when a
fact from its turn matches."""

from app.adapters.agent_memory.fact_lister import _fact
from app.adapters.sqlite import SqliteFactTags
from app.domain.errors import MemoryUnavailableError
from app.domain.ports.memory_capture import CaptureResult, ExtractedAttribute, FactTriple
from app.domain.ports.memory_recall import RecallHit
from app.services import capture_flow, vct_map
from app.services.ask_flow import Answer
from app.services.vct_tags import TagFilter, tag_answer

ME = "org/spreetail/user/mahamudul_hasan"
VMAP = vct_map.load()
TRIPLE = FactTriple("Quillfern Parcel", "company", "fuel_surcharge", "13.8%", "knowledge")


class FakeCapture:
    def __init__(self, passage_error: Exception | None = None) -> None:
        self.passage_error = passage_error
        self.calls: list[str] = []

    async def store_facts(self, facts: list[FactTriple], scope: str) -> CaptureResult:
        self.calls.append("store_facts")
        return CaptureResult(
            mode="stored",
            session_id="s1",
            attributes=[ExtractedAttribute("fuel_surcharge", "13.8%", "knowledge", "Q", "f1")],
        )

    async def store_passage(self, text: str, scope: str) -> str | None:
        self.calls.append("store_passage")
        if self.passage_error:
            raise self.passage_error
        return "turn-1"

    async def store(self, text: str, scope: str | None = None) -> CaptureResult:
        self.calls.append("store")
        return CaptureResult(
            mode="stored",
            session_id="s2",
            turn_id="turn-full",
            attributes=[ExtractedAttribute("rate", "6.2%", "knowledge", "Q", "f9")],
        )


def _preview(text: str = "Quillfern Parcel's fuel surcharge is now 13.8%.") -> capture_flow.Preview:
    fact = capture_flow.ReviewFact(
        id="p1",
        fact="Quillfern Parcel · fuel_surcharge = 13.8%",
        type="attribute",
        source="text",
        triple=TRIPLE,
    )
    return capture_flow.Preview(id="prev", owner="me@x.com", scope=ME, text=text, facts=[fact])


async def test_kept_facts_are_linked_to_the_text_stored_as_a_passage() -> None:
    capture = FakeCapture()
    tags = SqliteFactTags(":memory:")

    outcome = await capture_flow.store(
        capture,  # type: ignore[arg-type]
        _preview(),
        kept=["p1"],
        mode="triples",
        memory_category=None,
        links=tags,
    )

    assert outcome.written == 1
    assert capture.calls == ["store_facts", "store_passage"]
    assert await tags.facts_for_turns(["turn-1", "nope"]) == {"turn-1": ["f1"]}
    assert await tags.facts_for_turns([]) == {}


async def test_a_failed_passage_keeps_the_facts_and_skips_the_link() -> None:
    capture = FakeCapture(passage_error=MemoryUnavailableError("down"))
    tags = SqliteFactTags(":memory:")

    outcome = await capture_flow.store(
        capture,  # type: ignore[arg-type]
        _preview(),
        kept=["p1"],
        mode="triples",
        memory_category=None,
        links=tags,
    )

    assert outcome.written == 1
    assert await tags.facts_for_turns(["turn-1"]) == {}


async def test_blank_text_stores_no_passage_and_full_mode_links_its_turn() -> None:
    capture = FakeCapture()
    tags = SqliteFactTags(":memory:")

    await capture_flow.store(
        capture,  # type: ignore[arg-type]
        _preview("  "),
        kept=["p1"],
        mode="triples",
        memory_category=None,
        links=tags,
    )
    await capture_flow.extract(
        capture,  # type: ignore[arg-type]
        scope=ME,
        text="Quillfern raised rates 6.2%.",
        links=tags,
    )

    assert "store_passage" not in capture.calls
    assert await tags.facts_for_turns(["turn-full"]) == {"turn-full": ["f9"]}


def test_the_fact_listing_reads_the_turn_a_fact_came_from() -> None:
    from_turn = _fact({"id": "a1", "source": {"kind": "turn", "ref": "turn:t7"}, "scope": []})
    upsert = _fact({"id": "a2", "source": {"kind": "upsert"}, "scope": []})

    assert from_turn is not None
    assert from_turn.turn_id == "t7"
    assert upsert is not None
    assert upsert.turn_id is None


def _answer(*hits: RecallHit) -> Answer:
    return Answer(
        q="shipping costs", scopes=[ME], hits=list(hits), tier=None, trace_id=None, latency_ms=1
    )


async def test_a_chunk_passes_the_value_filter_through_its_facts() -> None:
    tags = SqliteFactTags(":memory:")
    await tags.save_auto("f1", ME, nodes=["sc6"], goals=["ff-mgmt5"], version="v1")
    await tags.save_auto("f2", ME, nodes=["sc4"], goals=["ff-mgmt1"], version="v1")
    await tags.link_turns([("f1", "turn-1", ME), ("f2", "turn-1", ME), ("f3", "turn-2", ME)])
    linked = RecallHit("memory_chunk:c1", "Weekly carrier notes", "memory_chunk", 0.5, "turn-1")
    orphan = RecallHit("memory_chunk:c2", "Team lunch is Friday.", "memory_chunk", 0.4, "turn-9")
    untagged = RecallHit("memory_chunk:c3", "Notes", "memory_chunk", 0.3, "turn-2")
    no_turn = RecallHit("chunk:d1", "A document passage", "chunk", 0.3)
    answer = _answer(linked, orphan, untagged, no_turn)

    plain = await tag_answer(answer, tags, VMAP, TagFilter())
    by_goal = await tag_answer(answer, tags, VMAP, TagFilter(goals=frozenset({"ff-mgmt1"})))
    none_match = await tag_answer(answer, tags, VMAP, TagFilter(nodes=frozenset({"fi4"})))

    # No filter: everything stays; the linked chunk shows its first fact's tags.
    assert plain.kept is None
    first = plain.tags["memory_chunk:c1"].node
    assert first is not None
    assert first.tag == "sc6"
    # Filter: the chunk passes through its second fact and shows that fact's tags.
    assert [h.id for h in by_goal.kept or []] == ["memory_chunk:c1"]
    matched = by_goal.tags["memory_chunk:c1"].goal
    assert matched is not None
    assert matched.tag == "ff-mgmt1"
    assert by_goal.removed_total == 3
    assert none_match.kept == []
