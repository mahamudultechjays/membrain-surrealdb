"""Ask: one recall per readable layer, in parallel, grouped org -> team -> personal.

Each layer is read with the key of the user it belongs to, through a lens on
that layer's path. A hit that shows up in more than one layer (a broad lens
can include narrower paths) is kept only in the most specific one.
"""

import asyncio
import time
from dataclasses import dataclass, field

from app.domain.errors import MemoryNotConfiguredError, MemoryUnavailableError
from app.domain.ports.memory_recall import RecallFactory, RecallHit, RecallResult
from app.services.scopes import LayerName, ScopeDirectory

LAYER_LIMITS: dict[LayerName, int] = {"org": 20, "team": 10, "personal": 10}
LAYER_ORDER: dict[LayerName, int] = {"org": 0, "team": 1, "personal": 2}
DOCUMENT_KINDS = frozenset({"chunk", "section"})


@dataclass(frozen=True, slots=True)
class LayerRead:
    layer: LayerName
    area: str
    # Scope whose key reads this layer.
    reader: str


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


def plan_reads(directory: ScopeDirectory, scopes: list[str]) -> list[LayerRead]:
    """Every layer the given scopes can read, once each, org first."""
    reads: dict[str, LayerRead] = {}
    for scope in scopes:
        for layer in directory.read_layers(scope):
            reads.setdefault(layer.path, LayerRead(layer.name, layer.path, scope))
    return sorted(reads.values(), key=lambda r: LAYER_ORDER[r.layer])


async def ask(
    recalls: RecallFactory, directory: ScopeDirectory, *, q: str, scopes: list[str]
) -> Answer:
    reads = plan_reads(directory, scopes)
    started = time.perf_counter()
    results = await asyncio.gather(
        *(
            recalls(read.reader).recall(q, lens=read.area, k=LAYER_LIMITS[read.layer])
            for read in reads
        ),
        return_exceptions=True,
    )
    latency_ms = round((time.perf_counter() - started) * 1000)

    failures = [r for r in results if isinstance(r, BaseException)]
    if failures and len(failures) == len(results):
        first = failures[0]
        if isinstance(first, (MemoryNotConfiguredError, MemoryUnavailableError)):
            raise first
        raise MemoryUnavailableError(str(first)) from first

    owners = {user.scope: user.name for user in directory.users()}
    seen: set[str] = set()
    answers: list[LayerAnswer] = []
    # Most specific layer first, so a hit is credited to the narrowest area.
    for read, result in reversed(list(zip(reads, results, strict=True))):
        owner = owners.get(read.area)
        if isinstance(result, BaseException):
            answers.append(LayerAnswer(read.layer, read.area, owner, error=str(result) or "failed"))
            continue
        hits = [hit for hit in result.hits if hit.id not in seen]
        seen.update(hit.id for hit in hits)
        answers.append(LayerAnswer(read.layer, read.area, owner, hits))
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
