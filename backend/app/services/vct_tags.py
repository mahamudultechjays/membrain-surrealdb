"""VCT tags on recall hits: look them up, and keep only hits that match a filter.

Recall hit ids carry a kind prefix ("attribute:<id>"); stored fact ids do not.
Only attribute hits (facts) can carry tags; entities and document passages
never match a tag filter. The rank 1 node and goal are the active tags.
Within one kind any chosen value matches (goal A or goal B); across kinds all
must match (a chosen goal and a chosen node). A domain matches through the
node's own domain.
"""

from dataclasses import dataclass, field, replace

from app.domain.ports.fact_tags import FactTag, FactTagRepository
from app.domain.ports.memory_recall import RecallHit
from app.domain.vct import VctMap
from app.services.ask_flow import LAYER_LIMITS, Answer

FACT_PREFIX = "attribute:"
# With a filter on, recall fetches this many times the usual number of hits,
# so enough survive the filter.
FILTER_WIDEN = 3


def fact_id_of(hit_id: str) -> str | None:
    """The stored fact id behind a recall hit, or None for non-fact hits."""
    return hit_id.removeprefix(FACT_PREFIX) if hit_id.startswith(FACT_PREFIX) else None


@dataclass(frozen=True, slots=True)
class HitTags:
    node: FactTag | None = None
    goal: FactTag | None = None


@dataclass(frozen=True, slots=True)
class TagFilter:
    goals: frozenset[str] = frozenset()
    nodes: frozenset[str] = frozenset()
    domains: frozenset[str] = frozenset()

    @property
    def active(self) -> bool:
        return bool(self.goals or self.nodes or self.domains)

    def unknown(self, vmap: VctMap) -> list[str]:
        """Filter values that are not on the metro map."""
        return sorted(
            [g for g in self.goals if vmap.goal(g) is None]
            + [n for n in self.nodes if vmap.node(n) is None]
            + [d for d in self.domains if vmap.domain(d) is None]
        )

    def matches(self, tags: HitTags | None, vmap: VctMap) -> bool:
        node = tags.node.tag if tags and tags.node else None
        goal = tags.goal.tag if tags and tags.goal else None
        if self.goals and goal not in self.goals:
            return False
        if self.nodes and node not in self.nodes:
            return False
        if self.domains:
            found = vmap.node(node) if node else None
            if found is None or found.domain_id not in self.domains:
                return False
        return True


@dataclass(frozen=True, slots=True)
class TaggedAnswer:
    answer: Answer
    # Active tags per recall hit id; hits without tags are absent.
    tags: dict[str, HitTags] = field(default_factory=dict)
    # Hits the filter dropped, per layer area, for the "compare" view.
    removed: dict[str, list[RecallHit]] = field(default_factory=dict)

    @property
    def removed_total(self) -> int:
        return sum(len(hits) for hits in self.removed.values())


async def tags_for_hits(repo: FactTagRepository, hit_ids: list[str]) -> dict[str, HitTags]:
    """Active tags per hit id, for the hits that are tagged facts."""
    ids = {hit_id: fid for hit_id in hit_ids if (fid := fact_id_of(hit_id))}
    stored = await repo.tags_for(list(dict.fromkeys(ids.values())))
    found = {hit_id: active_tags(stored.get(fid, [])) for hit_id, fid in ids.items()}
    return {k: v for k, v in found.items() if v.node or v.goal}


async def chunk_tags(repo: FactTagRepository, hits: list[RecallHit]) -> dict[str, list[HitTags]]:
    """For each memory chunk hit: the active tags of the facts from its turn.
    A chunk with no linked facts is absent (it never passes a value filter)."""
    chunks = [h for h in hits if h.kind == "memory_chunk" and h.turn_id]
    by_turn = await repo.facts_for_turns(list(dict.fromkeys(h.turn_id or "" for h in chunks)))
    fact_ids = list(dict.fromkeys(f for ids in by_turn.values() for f in ids))
    stored = await repo.tags_for(fact_ids)
    found: dict[str, list[HitTags]] = {}
    for hit in chunks:
        tags = [active_tags(stored.get(f, [])) for f in by_turn.get(hit.turn_id or "", [])]
        tags = [t for t in tags if t.node or t.goal]
        if tags:
            found[hit.id] = tags
    return found


async def tag_answer(
    answer: Answer, repo: FactTagRepository, vmap: VctMap, flt: TagFilter
) -> TaggedAnswer:
    """Attach active tags to every hit and, with a filter, keep only matches.

    A memory chunk passes when any fact extracted from (or captured with) its
    text matches, and shows that fact's tags; other untagged hits never pass.
    """
    hits = [h for layer in answer.layers for h in layer.hits]
    tags = await tags_for_hits(repo, [h.id for h in hits])
    via_facts = await chunk_tags(repo, hits)
    for hit_id, options in via_facts.items():
        tags[hit_id] = next((t for t in options if flt.matches(t, vmap)), options[0])
    if not flt.active:
        return TaggedAnswer(answer, tags)

    layers = []
    removed: dict[str, list[RecallHit]] = {}
    for layer in answer.layers:
        kept = [h for h in layer.hits if flt.matches(tags.get(h.id), vmap)]
        dropped = [h for h in layer.hits if h not in kept]
        if dropped:
            removed[layer.area] = dropped
        layers.append(replace(layer, hits=kept[: LAYER_LIMITS[layer.layer]]))
    return TaggedAnswer(replace(answer, layers=layers), tags, removed)


def active_tags(rows: list[FactTag]) -> HitTags:
    node = next((t for t in rows if t.kind == "node" and t.rank == 1), None)
    goal = next((t for t in rows if t.kind == "goal" and t.rank == 1), None)
    return HitTags(node, goal)
