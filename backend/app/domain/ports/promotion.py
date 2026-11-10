"""Port for promotion state kept in our backend (spec section 4).

statement: one fact found in a personal scope. fact_group: a topic people make
claims about. review_item: a candidate, flag or team rule. Scores and stages
are not stored; they are recomputed from statements each run.
"""

from dataclasses import dataclass
from typing import Literal, Protocol

from app.domain.promotion import Stance

Source = Literal["chat", "app"]
ReviewKind = Literal["candidate", "flag"]
ReviewStatus = Literal["open", "active", "closed", "rejected", "dropped", "kept"]


@dataclass(frozen=True, slots=True)
class Statement:
    user: str
    scope: str
    memory_ref: str
    source: Source
    text: str
    entity: str
    key: str
    value: str
    said_at: str
    id: int | None = None
    group_id: int | None = None
    stance: Stance | None = None
    # The value in the form its topic uses, from the grouping model.
    norm_value: str | None = None
    replaced_at: str | None = None
    processed_at: str | None = None


@dataclass(frozen=True, slots=True)
class FactGroup:
    label: str
    subject: str
    rule_entity_type: str
    rule_entity: str
    rule_key: str
    aliases: tuple[str, ...] = ()
    id: int | None = None
    created_at: str | None = None


@dataclass(frozen=True, slots=True)
class ReviewItem:
    kind: ReviewKind
    group_id: int
    value: str
    score_when_listed: float
    status: ReviewStatus
    id: int | None = None
    decided_by: str | None = None
    decided_at: str | None = None
    # The rule written to the team scope (active candidates).
    memory_ref: str | None = None
    # For a flag: the review_item id of the rule it questions.
    rule_id: int | None = None
    # The closing value written over a closed rule.
    closed_ref: str | None = None
    created_at: str | None = None
    # Where an approved rule was written, so closing it writes to the same place.
    rule_entity_type: str | None = None
    rule_entity: str | None = None
    rule_key: str | None = None


class PromotionRepository(Protocol):
    async def known_refs(self, refs: list[str]) -> set[str]: ...

    async def add_statements(self, rows: list[Statement]) -> int:
        """Adds rows whose memory_ref is new; returns how many were added."""
        ...

    async def mark_replaced(self, refs: list[str], at: str) -> int: ...

    async def live_refs(self, scopes: list[str]) -> set[str]:
        """memory_refs not replaced, in these scopes."""
        ...

    async def live_refs_except(self, scopes: list[str]) -> set[str]:
        """memory_refs not replaced, in any scope other than these."""
        ...

    async def revive(self, refs: list[str]) -> int:
        """Clears replaced_at for refs listed again; returns how many."""
        ...

    async def unprocessed(self, limit: int) -> list[Statement]: ...

    async def set_grouping(self, rows: list[tuple[int, int, str, Stance]], at: str) -> None:
        """(statement_id, group_id, norm_value, stance) for each grouped statement."""
        ...

    async def counted(self) -> list[Statement]:
        """Grouped statements that are not replaced."""
        ...

    async def groups(self) -> list[FactGroup]: ...

    async def groups_for_subjects(self, subjects: set[str]) -> list[FactGroup]: ...

    async def add_group(self, group: FactGroup) -> int: ...

    async def add_alias(self, group_id: int, alias: str) -> None: ...

    async def update_rule(
        self, group_id: int, *, label: str, entity_type: str, entity: str, key: str
    ) -> None: ...

    async def review_items(self) -> list[ReviewItem]: ...

    async def add_review_item(self, item: ReviewItem) -> int: ...

    async def set_status(
        self,
        item_id: int,
        status: ReviewStatus,
        *,
        expect: set[ReviewStatus],
        by: str | None = None,
        at: str | None = None,
        memory_ref: str | None = None,
        closed_ref: str | None = None,
        target: tuple[str, str, str] | None = None,
        score: float | None = None,
    ) -> ReviewItem:
        """Raises PromotionStateError when the item is not in one of `expect`.

        `target` (entity_type, entity, key) records where a rule was written;
        `score` replaces score_when_listed with the score at this decision.
        """
        ...

    async def closed_rule_refs(self) -> frozenset[str]:
        """Ids of closed team rules and their closing values, for Ask to skip."""
        ...
