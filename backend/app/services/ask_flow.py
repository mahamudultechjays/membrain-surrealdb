"""Ask: one recall across every readable scope, ranked by Agent Memory.

The scopes come from the asking user's grants. The recall goes through the one
admin key with a lens on each of those scopes, so nothing outside the grants is
read (a lens matches its exact path only, not the paths below it). Agent Memory
fuses and ranks the hits from all scopes into one list; we keep its order and
apply no layer precedence of our own.
"""

import time
from dataclasses import dataclass

from app.domain.ports.memory_recall import MemoryRecall, RecallHit
from app.domain.ports.user_scopes import LayerName, ScopeGrant

# Hits for the whole recall. Agent Memory's default is 10 and its maximum is 50.
RECALL_K = 20
LAYER_ORDER: dict[LayerName, int] = {"org": 0, "team": 1, "personal": 2}
DOCUMENT_KINDS = frozenset({"chunk", "section"})


@dataclass(frozen=True, slots=True)
class LayerRead:
    layer: LayerName
    area: str
    # Whose personal scope this is; None for org and team scopes.
    owner: str | None


@dataclass(frozen=True, slots=True)
class Answer:
    q: str
    scopes: list[str]
    hits: list[RecallHit]
    tier: str | None
    trace_id: str | None
    latency_ms: int


def plan_reads(grants: list[ScopeGrant]) -> list[LayerRead]:
    """Each granted scope once, org first, then team, then personal."""
    reads: dict[str, LayerRead] = {}
    for grant in grants:
        owner = grant.name if grant.layer == "personal" else None
        reads.setdefault(grant.scope_path, LayerRead(grant.layer, grant.scope_path, owner))
    return sorted(reads.values(), key=lambda r: (LAYER_ORDER[r.layer], r.area))


async def ask(
    recall: MemoryRecall,
    grants: list[ScopeGrant],
    *,
    q: str,
    skip: frozenset[str] = frozenset(),
) -> Answer:
    """Raises MemoryNotConfiguredError or MemoryUnavailableError when recall fails.

    `skip`: bare record ids left out of the answer (closed team rules and their
    closing values, from promotion).
    """
    scopes = [read.area for read in plan_reads(grants)]
    started = time.perf_counter()
    result = await recall.recall(q, lenses=scopes, k=RECALL_K)
    return Answer(
        q=q,
        scopes=scopes,
        hits=[h for h in result.hits if h.id.split(":", 1)[-1] not in skip],
        tier=result.tier or None,
        trace_id=result.trace_id,
        latency_ms=round((time.perf_counter() - started) * 1000),
    )


def source_kind(hit: RecallHit) -> str:
    return "document" if hit.kind in DOCUMENT_KINDS else "memory"
