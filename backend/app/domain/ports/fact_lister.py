"""Port for paging through stored facts, newest first, for the VCT tagger.

Agent Memory has no read-by-id for facts, but its listing returns each current
fact's id, text and scopes, and the id of the older fact it replaced.
"""

from dataclasses import dataclass, field
from typing import Protocol


@dataclass(frozen=True, slots=True)
class ListedFact:
    id: str
    # What the tagger matches on: Agent Memory's one-sentence summary, or
    # "<entity> <key> <value>" when there is none.
    text: str
    scopes: tuple[str, ...]
    # The older fact this one superseded, if any.
    supersedes: str | None = None
    # The captured turn the fact was extracted from; None for facts written
    # directly as triples.
    turn_id: str | None = None


@dataclass(frozen=True, slots=True)
class ListedPage:
    facts: list[ListedFact] = field(default_factory=list)
    # None on the last page.
    cursor: str | None = None


class FactLister(Protocol):
    async def page(self, scopes: list[str], *, limit: int, cursor: str | None) -> ListedPage:
        """One page of the current facts readable in these scopes, newest first."""
        ...
