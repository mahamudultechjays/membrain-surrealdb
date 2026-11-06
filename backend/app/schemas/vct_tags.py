"""VCT tag schemas shared by Ask, Brain and the tag editor."""

from typing import Literal

from pydantic import BaseModel

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
