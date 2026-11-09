"""VCT tag schemas shared by Ask, Brain and the tag editor."""

from typing import Literal

from pydantic import BaseModel, Field

from app.domain.ports.fact_tags import FactTag
from app.domain.vct import VctMap
from app.services.vct_tags import HitTags


class TagRef(BaseModel):
    kind: Literal["node", "goal"]
    id: str
    name: str
    section_id: str
    section: str | None
    # A node's domain; goals belong to sections only.
    domain_id: str | None = None
    domain: str | None = None
    # "auto" from the tagger, "user" when a person set or confirmed it.
    source: Literal["auto", "user"]
    rank: int = 1


class FactTagsOut(BaseModel):
    node: TagRef | None = None
    goal: TagRef | None = None


class TagEditRequest(BaseModel):
    """change: pick `tag` as this kind's active tag; remove: drop this kind;
    accept: confirm this kind. Review actions take no kind: confirm (node and
    goal), not_business, keep (reviewed, nothing changed) and tag_guesses (make
    the best guesses of a not-business fact its tags)."""

    action: Literal["change", "remove", "accept", "confirm", "not_business", "keep", "tag_guesses"]
    kind: Literal["node", "goal"] | None = None
    tag: str | None = Field(default=None, max_length=40)


class ReviewBulkRequest(BaseModel):
    fact_ids: list[str] = Field(min_length=1, max_length=200)
    action: Literal["confirm", "keep"]


class ReviewBulkResponse(BaseModel):
    done: list[str]
    # Facts left out: not tagged yet, or in a scope the caller can't read.
    skipped: list[str]


class FactTagDetail(BaseModel):
    fact_id: str
    scope: str
    # False when the tagger judged it not business; adding a tag makes it business.
    business: bool = True
    tagged_at: str | None = None
    reviewed_at: str | None = None
    reviewed_by: str | None = None
    # A not-business fact's best matches, for "Tag it"; empty otherwise.
    guess_nodes: list[TagRef] = Field(default_factory=list)
    guess_goals: list[TagRef] = Field(default_factory=list)
    # Rank order: [0] is active, the rest are the tagger's alternatives.
    nodes: list[TagRef]
    goals: list[TagRef]


class CoverageCount(BaseModel):
    id: str
    facts: int


class CoverageCell(BaseModel):
    domain_id: str
    section_id: str
    # How many map nodes sit in this cell, and how many facts they carry.
    nodes: int
    facts: int


class VctCoverage(BaseModel):
    scopes: list[str]
    tagged_facts: int
    without_goal: int
    not_business: int = 0
    nodes: list[CoverageCount]
    goals: list[CoverageCount]
    cells: list[CoverageCell]


def tag_ref(tag: FactTag, vmap: VctMap) -> TagRef | None:
    """A stored tag with its names from the metro map; None if the map lost it."""
    if tag.kind == "node":
        node = vmap.node(tag.tag)
        if node is None:
            return None
        section = vmap.section(node.section_id)
        domain = vmap.domain(node.domain_id)
        return TagRef(
            kind="node",
            id=node.id,
            name=node.name,
            section_id=node.section_id,
            section=section.label if section else None,
            domain_id=node.domain_id,
            domain=domain.name if domain else None,
            source=tag.source,
            rank=tag.rank,
        )
    goal = vmap.goal(tag.tag)
    if goal is None:
        return None
    section = vmap.section(goal.section_id)
    return TagRef(
        kind="goal",
        id=goal.id,
        name=goal.name,
        section_id=goal.section_id,
        section=section.label if section else None,
        source=tag.source,
        rank=tag.rank,
    )


def fact_tags_out(tags: HitTags | None, vmap: VctMap) -> FactTagsOut | None:
    if tags is None:
        return None
    node = tag_ref(tags.node, vmap) if tags.node else None
    goal = tag_ref(tags.goal, vmap) if tags.goal else None
    return FactTagsOut(node=node, goal=goal) if node or goal else None
