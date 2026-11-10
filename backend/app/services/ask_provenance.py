"""Trust and provenance for the facts an Ask answer recalled.

/query returns no trust, but each attribute hit names its entity and key, and
the entity's record holds every attribute's trust, confidence and history.
Only attribute hits that really match the question (at or above `min_score`)
are looked up, one GET per distinct entity, in parallel. Each result is kept
only for the hit ids already recalled: an entity's record spans every scope,
and the asker may not read them all.
"""

import asyncio
import logging

from app.domain.ports.fact_provenance import FactProvenance, FactProvenanceReader
from app.services.ask_flow import Answer

logger = logging.getLogger(__name__)


async def lookup(
    reader: FactProvenanceReader,
    answer: Answer,
    *,
    min_score: float,
    max_entities: int,
) -> dict[str, FactProvenance]:
    """Hit id -> provenance, for the attribute hits worth showing trust on.

    Never raises: a failed lookup leaves those hits without provenance.
    """
    hits = [
        hit
        for layer in answer.layers
        for hit in layer.hits
        if hit.kind == "attribute"
        and hit.entity_type
        and hit.entity_name
        and hit.score >= min_score
    ]
    entities = list(dict.fromkeys((h.entity_type or "", h.entity_name or "") for h in hits))
    if len(entities) > max_entities:
        logger.info(
            "Ask provenance: %d entities, looking up the first %d", len(entities), max_entities
        )
        entities = entities[:max_entities]
    results = await asyncio.gather(
        *(reader.attributes(entity_type, name) for entity_type, name in entities),
        return_exceptions=True,
    )
    by_entity: dict[tuple[str, str], dict[str, FactProvenance]] = {}
    for entity, result in zip(entities, results, strict=True):
        if isinstance(result, BaseException):
            logger.warning("Ask provenance for %s/%s failed: %s", *entity, result)
            continue
        by_entity[entity] = result

    out: dict[str, FactProvenance] = {}
    for hit in hits:
        attributes = by_entity.get((hit.entity_type or "", hit.entity_name or ""), {})
        # Hit ids carry the table ("attribute:abc"); the entity record uses the bare id.
        found = attributes.get(hit.id.split(":", 1)[-1])
        if found is not None:
            out[hit.id] = found
    return out
