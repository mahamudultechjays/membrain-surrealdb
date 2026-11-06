"""Ask: one recall per readable scope, in parallel, grouped org -> team -> personal.

The scopes come from the asking user's grants. Every recall goes through the
one admin key with a lens on exactly that scope, so nothing outside the grants
is read (a lens matches its exact path only, not the paths below it). A hit
that shows up in more than one scope is kept only in the most specific one.
"""

import asyncio
import time
from dataclasses import dataclass, field

from app.domain.errors import MemoryNotConfiguredError, MemoryUnavailableError
from app.domain.ports.memory_recall import MemoryRecall, RecallHit, RecallResult
from app.domain.ports.user_scopes import LayerName, ScopeGrant

LAYER_LIMITS: dict[LayerName, int] = {"org": 20, "team": 10, "personal": 10}
LAYER_ORDER: dict[LayerName, int] = {"org": 0, "team": 1, "personal": 2}
DOCUMENT_KINDS = frozenset({"chunk", "section"})


@dataclass(frozen=True, slots=True)
class LayerRead:
    layer: LayerName
    area: str
    # Whose personal scope this is; None for org and team scopes.
    owner: str | None


@dataclass(frozen=True, slots=True)
class LayerAnswer:
    layer: LayerName
    area: str
    owner: str | None
    hits: list[RecallHit] = field(default_factory=list)
    error: str | None = None


@dataclass(frozen=True, slots=True)
class Answer:
    q: str
    layers: list[LayerAnswer]
    tiers: list[str]
    trace_ids: list[str]
    latency_ms: int

    @property
    def total_facts(self) -> int:
        return sum(len(layer.hits) for layer in self.layers)


def plan_reads(grants: list[ScopeGrant]) -> list[LayerRead]:
    """Each granted scope once, org first, then team, then personal."""
    reads: dict[str, LayerRead] = {}
    for grant in grants:
        owner = grant.name if grant.layer == "personal" else None
        reads.setdefault(grant.scope_path, LayerRead(grant.layer, grant.scope_path, owner))
    return sorted(reads.values(), key=lambda r: (LAYER_ORDER[r.layer], r.area))


async def ask(recall: MemoryRecall, grants: list[ScopeGrant], *, q: str, widen: int = 1) -> Answer:
    """`widen` multiplies each layer's recall size, for callers that filter after."""
    reads = plan_reads(grants)
    started = time.perf_counter()
    results = await asyncio.gather(
        *(recall.recall(q, lens=read.area, k=LAYER_LIMITS[read.layer] * widen) for read in reads),
        return_exceptions=True,
    )
    latency_ms = round((time.perf_counter() - started) * 1000)

    failures = [r for r in results if isinstance(r, BaseException)]
    if failures and len(failures) == len(results):
        first = failures[0]
        if isinstance(first, (MemoryNotConfiguredError, MemoryUnavailableError)):
            raise first
        raise MemoryUnavailableError(str(first)) from first

    seen: set[str] = set()
    answers: list[LayerAnswer] = []
    # Most specific layer first, so a hit is credited to the narrowest scope.
    for read, result in reversed(list(zip(reads, results, strict=True))):
        if isinstance(result, BaseException):
            error = str(result) or "failed"
            answers.append(LayerAnswer(read.layer, read.area, read.owner, error=error))
            continue
        hits = [hit for hit in result.hits if hit.id not in seen]
        seen.update(hit.id for hit in hits)
        answers.append(LayerAnswer(read.layer, read.area, read.owner, hits))
    answers.reverse()

    ok = [r for r in results if isinstance(r, RecallResult)]
    return Answer(
        q=q,
        layers=answers,
        tiers=sorted({r.tier for r in ok if r.tier}),
        trace_ids=[r.trace_id for r in ok if r.trace_id],
        latency_ms=latency_ms,
    )


def source_kind(hit: RecallHit) -> str:
    return "document" if hit.kind in DOCUMENT_KINDS else "memory"
