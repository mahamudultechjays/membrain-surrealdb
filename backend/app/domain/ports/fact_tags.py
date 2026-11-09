"""Port for VCT tags on Agent Memory facts.

Only fact ids and tags are kept here, never fact text: the facts themselves stay
in Agent Memory. A fact gets up to 3 node and 3 goal tags; rank 1 is the active
tag that filters use, ranks 2-3 are alternatives shown in the editor. Tags set
by a person (source "user") are never overwritten by the tagger.
A fact the tagger judges "not business" (a decoy passage ranked first) is
processed but gets no tags, until a person adds one.
"""

from dataclasses import dataclass, field
from typing import Literal, Protocol

TagKind = Literal["node", "goal"]
TagSource = Literal["auto", "user"]
TagAction = Literal["add", "change", "remove", "accept"]

TAG_KINDS: tuple[TagKind, ...] = ("node", "goal")


@dataclass(frozen=True, slots=True)
class FactTag:
    fact_id: str
    scope: str
    kind: TagKind
    tag: str
    rank: int
    source: TagSource
    # The tagger version that wrote it; None for tags a person set.
    tagger_version: str | None
    updated_by: str
    updated_at: str


@dataclass(frozen=True, slots=True)
class TagCount:
    kind: TagKind
    tag: str
    facts: int


@dataclass(frozen=True, slots=True)
class FeedbackStats:
    # All user edits in the window, and how many of them corrected the tagger.
    edits: int
    corrections: int
    # (old tag, new tag, times), most frequent first; removals have new None.
    confusions: list[tuple[str, str | None, int]] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class ReviewState:
    # When the tagger last tagged the fact, and when a person reviewed it.
    tagged_at: str
    reviewed_at: str | None = None
    reviewed_by: str | None = None


class FactTagRepository(Protocol):
    async def tags_for(self, fact_ids: list[str]) -> dict[str, list[FactTag]]:
        """All tags of these facts, by fact id, in rank order; facts with none are absent."""
        ...

    async def processed(self, fact_ids: list[str]) -> set[str]:
        """Which of these facts the tagger has already handled (even if a person
        later removed every tag)."""
        ...

    async def not_business(self, fact_ids: list[str]) -> set[str]:
        """Which of these facts the tagger marked "not business"."""
        ...

    async def scope_of(self, fact_id: str) -> str | None:
        """The scope a processed fact belongs to, or None if never processed."""
        ...

    async def save_auto(
        self,
        fact_id: str,
        scope: str,
        *,
        nodes: list[str],
        goals: list[str],
        version: str,
        business: bool = True,
    ) -> None:
        """Store the tagger's ranked matches and mark the fact processed.

        A kind that already has a tag set by a person is left untouched. With
        `business` False the tagger's own tags are cleared instead.
        """
        ...

    async def copy_user_tags(self, old_fact_id: str, new_fact_id: str, scope: str) -> int:
        """Carry a person's tags from a superseded fact to its new version.

        Returns how many tags were copied.
        """
        ...

    async def set_tag(self, fact_id: str, kind: TagKind, tag: str, user: str) -> None:
        """A person picks the tag for this kind; it becomes rank 1, the others go."""
        ...

    async def remove(self, fact_id: str, kind: TagKind, user: str) -> None:
        """A person removes this kind's tags from the fact."""
        ...

    async def accept(self, fact_id: str, kind: TagKind, user: str) -> None:
        """A person confirms the rank 1 tag, so the tagger never replaces it."""
        ...

    async def confirm(self, fact_id: str, user: str) -> None:
        """A person confirms both the node and the goal (review "Confirm")."""
        ...

    async def mark_not_business(self, fact_id: str, user: str) -> None:
        """A person says the fact is not business: its tags become guesses."""
        ...

    async def keep(self, fact_id: str, user: str) -> None:
        """A person reviewed the fact and changed nothing (e.g. keeps not business)."""
        ...

    async def guesses(self, fact_id: str) -> dict[TagKind, list[str]]:
        """The tagger's best nodes and goals for a not-business fact, ranked."""
        ...

    async def link_turns(self, links: list[tuple[str, str, str]]) -> None:
        """Record (fact id, turn id, scope): the captured text each fact came from."""
        ...

    async def facts_for_turns(self, turn_ids: list[str]) -> dict[str, list[str]]:
        """The fact ids linked to each of these turns."""
        ...

    async def review_state(self, fact_ids: list[str]) -> dict[str, ReviewState]:
        """When each processed fact was tagged, and reviewed if it was."""
        ...

    async def counts(self, scopes: list[str]) -> list[TagCount]:
        """How many facts carry each rank 1 tag, over these scopes only."""
        ...

    async def totals(self, scopes: list[str]) -> tuple[int, int, int]:
        """(processed facts, business facts with no goal, not-business facts)
        over these scopes."""
        ...

    async def without(self, kind: TagKind, scopes: list[str], limit: int, offset: int) -> list[str]:
        """Processed business fact ids in these scopes with no tag of this kind,
        newest first."""
        ...

    async def feedback_stats(self, since: str) -> FeedbackStats:
        """User edits since this ISO time."""
        ...
