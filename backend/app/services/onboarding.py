"""Onboarding: map a user's description of their work to VCT nodes, then to domains.

The 41 nodes are stored once as passages in a matcher-only scope (VCT_SCOPE,
granted to no user). Each clause of the user's description is recalled against
that scope and the top nodes become candidates. Recall scores are rank
positions, not similarity (spike, 3 Nov), so nothing is accepted by score:
the user confirms the nodes, and their domains follow from the map.
"""

import asyncio
import re
from dataclasses import dataclass

from app.domain.errors import UnknownVctNodeError, VctNotSeededError
from app.domain.ports.memory_recall import MemoryRecall
from app.domain.ports.onboarding import (
    ConfirmedBy,
    MappedNode,
    OnboardingRecord,
    OnboardingRepository,
)
from app.domain.ports.passage_writer import PassageWriter
from app.domain.ports.scope_registry import ScopeRegistry
from app.domain.vct import VctMap, VctNode

CANDIDATES_PER_CLAUSE = 3
MAX_CLAUSES = 8
MAX_NODES = 8  # as membrain's onboarding mapper (_TOP_N)
_RECALL_K = 10  # extra hits, since one node can come back as several passages
_SEED_CONCURRENCY = 8

_NODE_TAG = re.compile(r"VCT node \[([a-z0-9-]+)\]")


@dataclass(frozen=True, slots=True)
class ClauseMatch:
    clause: str
    candidates: list[VctNode]


def node_text(node: VctNode) -> str:
    """The passage stored for a node; the [id] tag maps a recall hit back to it."""
    keywords = f" Keywords: {', '.join(node.keywords)}." if node.keywords else ""
    return f"VCT node [{node.id}] {node.name}. {node.description}.{keywords}"


def split_clauses(text: str) -> list[str]:
    """Sentences, then comma and "and" parts, as membrain's mapper does.

    Parts under three words are dropped; a short description is kept whole.
    """
    parts = [
        piece.strip()
        for sentence in re.split(r"[.!?;\n]+", text)
        for piece in re.split(r",|\band\b", sentence)
    ]
    clauses = [p for p in parts if len(p.split()) >= 3]
    if not clauses and text.strip():
        clauses = [text.strip()]
    return clauses[:MAX_CLAUSES]


class OnboardingService:
    def __init__(
        self,
        repo: OnboardingRepository,
        recall: MemoryRecall,
        passages: PassageWriter,
        registry: ScopeRegistry,
        vct_map: VctMap,
        *,
        vct_scope: str,
    ) -> None:
        self._repo = repo
        self._recall = recall
        self._passages = passages
        self._registry = registry
        self.map = vct_map
        self._scope = vct_scope.strip("/")

    async def get(self, email: str) -> OnboardingRecord | None:
        return await self._repo.get(email)

    async def suggest(self, primary_work: str) -> list[ClauseMatch]:
        """Candidate nodes per clause, best first. Raises VctNotSeededError when
        nothing comes back at all."""
        clauses = split_clauses(primary_work)
        matches = await asyncio.gather(*(self._match(c) for c in clauses))
        if clauses and not any(m.candidates for m in matches):
            raise VctNotSeededError(self._scope)
        return list(matches)

    async def confirm(
        self,
        email: str,
        *,
        primary_work: str,
        node_ids: list[str],
        primary_node_id: str | None = None,
        role: str | None = None,
        team: str | None = None,
        by: ConfirmedBy = "user",
    ) -> OnboardingRecord:
        """Save the chosen nodes in order; the primary defaults to the first."""
        ids = list(dict.fromkeys(node_ids))
        unknown = [i for i in ids if self.map.node(i) is None]
        if unknown:
            raise UnknownVctNodeError(f"unknown nodes: {', '.join(unknown)}")
        if len(ids) > MAX_NODES:
            raise UnknownVctNodeError(f"at most {MAX_NODES} nodes")
        primary = primary_node_id or (ids[0] if ids else None)
        if primary is not None and primary not in ids:
            raise UnknownVctNodeError(f"primary {primary} is not one of the chosen nodes")
        record = OnboardingRecord(
            email=email.strip().lower(),
            primary_work=primary_work.strip(),
            role=role,
            team=team,
            nodes=[
                MappedNode(node_id=i, rank=rank, is_primary=i == primary, confirmed_by=by)
                for rank, i in enumerate(ids, start=1)
            ],
        )
        await self._repo.save(record)
        return await self._repo.get(email) or record

    async def seed(self, *, force: bool = False) -> int:
        """Store every node as a passage in the matcher scope, once.

        Returns how many were written: 0 when the scope already exists, unless
        `force` (re-seeding duplicates passages; matching de-duplicates by id).
        """
        if self._scope in await self._registry.list(self._scope) and not force:
            return 0
        await self._registry.ensure(self._scope)
        gate = asyncio.Semaphore(_SEED_CONCURRENCY)

        async def write(node: VctNode) -> None:
            async with gate:
                await self._passages.write(node_text(node), self._scope)

        await asyncio.gather(*(write(n) for n in self.map.nodes))
        return len(self.map.nodes)

    async def _match(self, clause: str) -> ClauseMatch:
        result = await self._recall.recall(clause, lens=self._scope, k=_RECALL_K)
        ids: dict[str, None] = {}
        for hit in result.hits:
            tag = _NODE_TAG.search(hit.text or "")
            if tag and self.map.node(tag.group(1)):
                ids.setdefault(tag.group(1))
        nodes = [n for i in list(ids)[:CANDIDATES_PER_CLAUSE] if (n := self.map.node(i))]
        return ClauseMatch(clause=clause, candidates=nodes)
