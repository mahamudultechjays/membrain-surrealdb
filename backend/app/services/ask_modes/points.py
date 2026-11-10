"""Finding facts that disagree across scopes.

Recall hits carry only an id, a score, a kind and text. Attribute hits read
"<Entity>'s <key> is <value>" (live shape) or "<entity> · <key> = <value>"
(the older mock shape), so the entity, key and value are parsed back out of
the text. Passages and entity names are never grouped.

Two hits are about the same point when their entities match (equal, or one's
words are a subset of the other's) and their keys match after normalising
plurals and a few synonyms. Keys worded differently, such as "return policy"
and "returns window", do not match: that is a known gap.
"""

import re
from dataclasses import dataclass, replace
from typing import Literal

from app.domain.ports.memory_recall import RecallHit
from app.domain.ports.user_scopes import LayerName
from app.services.ask_flow import LAYER_ORDER, Answer

LIVE_SHAPE = re.compile(r"^(?P<entity>.+?)'s (?P<key>.+?) is (?P<value>.+)$", re.DOTALL)
MOCK_SHAPE = re.compile(r"^(?P<entity>.+?) · (?P<key>.+?) = (?P<value>.+)$", re.DOTALL)
KEY_SYNONYMS = {"max": "maximum", "min": "minimum", "qty": "quantity"}
KEY_STOPWORDS = frozenset({"the", "of", "a", "an", "for", "per"})
LAYER_LABELS: dict[LayerName, str] = {"org": "Org", "team": "Team", "personal": "Personal"}


@dataclass(frozen=True, slots=True)
class FactVerdict:
    status: Literal["used", "set_aside"]
    reason: str


@dataclass(frozen=True, slots=True)
class ConflictValue:
    value: str
    layers: list[LayerName]
    areas: list[str]
    hit_ids: list[str]
    best_score: float


@dataclass(frozen=True, slots=True)
class Conflict:
    id: str
    entity: str
    key: str
    # Highest-scoring value first.
    values: list[ConflictValue]
    # Set by best_match only.
    winner_hit_id: str | None = None
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class Parsed:
    entity: str
    key: str
    value: str


@dataclass(frozen=True, slots=True)
class Located:
    """A parsed hit and the scope it was read from."""

    hit: RecallHit
    parsed: Parsed
    layer: LayerName
    area: str
    entity_words: frozenset[str]
    key_words: frozenset[str]
    norm_value: str


def parse(hit: RecallHit) -> Parsed | None:
    """Entity, key and value of an attribute hit; None for anything else."""
    text = hit.text.strip()
    match = MOCK_SHAPE.match(text)
    if match is None and hit.kind == "attribute":
        match = LIVE_SHAPE.match(text)
    if match is None:
        return None
    return Parsed(match["entity"].strip(), match["key"].strip(), match["value"].strip())


def entity_words(entity: str) -> frozenset[str]:
    return frozenset(re.sub(r"[^a-z0-9]+", " ", entity.lower()).split())


def key_words(key: str) -> frozenset[str]:
    words = set()
    for word in re.split(r"[^a-z0-9]+", key.lower()):
        if not word or word in KEY_STOPWORDS:
            continue
        word = KEY_SYNONYMS.get(word, word)
        if len(word) > 3 and word.endswith("s") and not word.endswith("ss"):
            word = word[:-1]
        words.add(word)
    return frozenset(words)


def normalize_value(value: str) -> str:
    return " ".join(value.lower().split()).rstrip(" .;,:!")


def same_point(a: Located, b: Located) -> bool:
    entities = (
        a.entity_words == b.entity_words
        or a.entity_words <= b.entity_words
        or b.entity_words <= a.entity_words
    )
    return bool(a.entity_words and b.entity_words) and entities and a.key_words == b.key_words


def locate(answer: Answer) -> list[Located]:
    """Every parseable hit of every layer that answered."""
    located: list[Located] = []
    for layer in answer.layers:
        for hit in layer.hits:
            parsed = parse(hit)
            if parsed is None:
                continue
            located.append(
                Located(
                    hit,
                    parsed,
                    layer.layer,
                    layer.area,
                    entity_words(parsed.entity),
                    key_words(parsed.key),
                    normalize_value(parsed.value),
                )
            )
    return located


def find_conflicts(
    answer: Answer, *, min_score: float = 0.0
) -> tuple[list[Conflict], dict[str, list[Located]]]:
    """Conflicts across scopes, plus each conflict's hits keyed by conflict id.

    A conflict counts only when at least one of its hits scores `min_score` or
    more. Agent Memory fills a small scope's results with every record it holds,
    scored by rank (0.380, 0.374, 0.368...), so without this floor every question
    would flag every disagreement in the scope.
    """
    located = locate(answer)
    parent = list(range(len(located)))

    def root(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for i in range(len(located)):
        for j in range(i + 1, len(located)):
            if same_point(located[i], located[j]):
                parent[root(i)] = root(j)

    groups: dict[int, list[Located]] = {}
    for i, item in enumerate(located):
        groups.setdefault(root(i), []).append(item)

    found: list[tuple[float, Conflict, list[Located]]] = []
    for members in groups.values():
        if len({m.norm_value for m in members}) < 2 or len({m.area for m in members}) < 2:
            continue
        if max(m.hit.score for m in members) < min_score:
            continue
        found.append((max(m.hit.score for m in members), _conflict(members), members))

    found.sort(key=lambda entry: -entry[0])
    conflicts: list[Conflict] = []
    members_by_id: dict[str, list[Located]] = {}
    for n, (_, conflict, members) in enumerate(found, start=1):
        cid = f"c{n}"
        conflicts.append(replace(conflict, id=cid))
        members_by_id[cid] = members
    return conflicts, members_by_id


def _conflict(members: list[Located]) -> Conflict:
    by_value: dict[str, list[Located]] = {}
    for m in members:
        by_value.setdefault(m.norm_value, []).append(m)
    values = [
        ConflictValue(
            value=holders[0].parsed.value,
            layers=sorted({h.layer for h in holders}, key=lambda name: LAYER_ORDER[name]),
            areas=list(dict.fromkeys(h.area for h in holders)),
            hit_ids=[h.hit.id for h in holders],
            best_score=max(h.hit.score for h in holders),
        )
        for holders in by_value.values()
    ]
    values.sort(key=lambda v: -v.best_score)
    shortest = min(members, key=lambda m: len(m.parsed.entity))
    return Conflict("", shortest.parsed.entity, shortest.parsed.key, values)
