"""The Spreetail value-chain (VCT) metro map: nodes grouped into domains.

A user is mapped to nodes at onboarding; each node belongs to exactly one domain.
"""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class VctNode:
    id: str
    name: str
    description: str
    domain_id: str
    section_id: str
    keywords: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class VctDomain:
    id: str
    name: str
    node_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class VctMap:
    topology_version: str
    domains: tuple[VctDomain, ...]
    nodes: tuple[VctNode, ...]

    def node(self, node_id: str) -> VctNode | None:
        return next((n for n in self.nodes if n.id == node_id), None)

    def domain(self, domain_id: str) -> VctDomain | None:
        return next((d for d in self.domains if d.id == domain_id), None)

    def domains_of(self, node_ids: list[str]) -> list[VctDomain]:
        """The domains of these nodes, first-seen order, each once."""
        ids = dict.fromkeys(n.domain_id for i in node_ids if (n := self.node(i)))
        return [d for i in ids if (d := self.domain(i))]
